# -*- coding: utf-8 -*-

import configparser
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
CONFIG_PATH = ROOT / "config" / "config.ini"
TELEGRAM_APPS_URL = "https://my.telegram.org/auth?to=apps"


class TrackerApp(tk.Tk):
	def __init__(self):
		super().__init__()
		self.title("Telegram Tracker Light")
		self.geometry("1280x820")
		self.minsize(1120, 720)
		self.output_queue = queue.Queue()
		self.running_process = None
		self._build_style()
		self._build_layout()
		self._load_config()
		self._poll_output()

	def _build_style(self):
		style = ttk.Style(self)
		try:
			style.theme_use("clam")
		except tk.TclError:
			pass
		style.configure("TFrame", background="#f5f7fa")
		style.configure("TLabel", background="#f5f7fa", foreground="#20242a", font=("Segoe UI", 10))
		style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
		style.configure("Subtle.TLabel", foreground="#606a78")
		style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
		style.configure("Primary.TButton", background="#0f766e", foreground="#ffffff")
		style.configure("TNotebook", background="#f5f7fa", borderwidth=0)
		style.configure("TNotebook.Tab", padding=(14, 8), font=("Segoe UI", 10))
		style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
		style.configure("Card.TLabel", background="#ffffff")

	def _build_layout(self):
		self.columnconfigure(0, weight=1)
		self.rowconfigure(1, weight=1)

		header = ttk.Frame(self, padding=(18, 16, 18, 8))
		header.grid(row=0, column=0, sticky="ew")
		header.columnconfigure(0, weight=1)
		ttk.Label(header, text="Telegram Tracker Light", style="Header.TLabel").grid(row=0, column=0, sticky="w")
		ttk.Label(
			header,
			text="Panel local para configurar, capturar, buscar y analizar canales de Telegram.",
			style="Subtle.TLabel",
		).grid(row=1, column=0, sticky="w", pady=(4, 0))
		self.status_var = tk.StringVar(value="Listo")
		ttk.Label(header, textvariable=self.status_var, style="Subtle.TLabel").grid(row=0, column=1, sticky="e")

		main = ttk.PanedWindow(self, orient=tk.VERTICAL)
		main.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))

		self.tabs = ttk.Notebook(main)
		main.add(self.tabs, weight=3)

		self._build_setup_tab()
		self._build_capture_tab()
		self._build_search_tab()
		self._build_analysis_tab()
		self._build_network_tab()

		console_frame = ttk.Frame(main, padding=(0, 10, 0, 0))
		console_frame.rowconfigure(1, weight=1)
		console_frame.columnconfigure(0, weight=1)
		toolbar = ttk.Frame(console_frame)
		toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
		ttk.Label(toolbar, text="Salida de ejecucion").pack(side=tk.LEFT)
		ttk.Button(toolbar, text="Limpiar", command=self._clear_console).pack(side=tk.RIGHT)
		ttk.Button(toolbar, text="Detener", command=self._stop_process).pack(side=tk.RIGHT, padx=(0, 8))
		self.console = tk.Text(console_frame, height=11, wrap="word", bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb")
		self.console.grid(row=1, column=0, sticky="nsew")
		input_bar = ttk.Frame(console_frame)
		input_bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
		input_bar.columnconfigure(1, weight=1)
		ttk.Label(input_bar, text="Entrada a consola").grid(row=0, column=0, sticky="w", padx=(0, 8))
		self.process_input_var = tk.StringVar()
		self.process_input_entry = ttk.Entry(input_bar, textvariable=self.process_input_var)
		self.process_input_entry.grid(row=0, column=1, sticky="ew")
		self.process_input_entry.bind("<Return>", lambda event: self._send_process_input())
		ttk.Button(input_bar, text="Enviar", command=self._send_process_input).grid(row=0, column=2, padx=(8, 0))
		main.add(console_frame, weight=1)

	def _card(self, parent, title, row, column, columnspan=1):
		frame = ttk.Frame(parent, style="Card.TFrame", padding=16)
		frame.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=8, pady=8)
		frame.columnconfigure(1, weight=1)
		frame.columnconfigure(2, weight=0)
		ttk.Label(frame, text=title, style="Card.TLabel", font=("Segoe UI", 12, "bold")).grid(
			row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
		)
		return frame

	def _entry(self, parent, label, variable, row, show=None):
		ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=5)
		entry = ttk.Entry(parent, textvariable=variable, show=show)
		entry.grid(row=row, column=1, sticky="ew", pady=5, padx=(10, 0))
		return entry

	def _secret_entry(self, parent, label, variable, row):
		ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=5)
		entry = tk.Entry(
			parent,
			textvariable=variable,
			show="*",
			borderwidth=1,
			relief="solid",
			font=("Segoe UI", 10),
			bg="#ffffff",
			fg="#20242a",
			insertbackground="#20242a",
		)
		entry.grid(row=row, column=1, sticky="ew", pady=5, padx=(10, 0), ipady=4)
		return entry

	def _build_setup_tab(self):
		tab = ttk.Frame(self.tabs, padding=10)
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)
		tab.rowconfigure(0, weight=1)
		self.tabs.add(tab, text="Configuracion")

		card = self._card(tab, "Credenciales de Telegram", 0, 0)
		self.api_id_var = tk.StringVar()
		self.api_hash_var = tk.StringVar()
		self.phone_var = tk.StringVar()
		self.show_credentials_var = tk.BooleanVar(value=False)
		self.api_id_entry = self._secret_entry(card, "api_id", self.api_id_var, 1)
		self.api_hash_entry = self._secret_entry(card, "api_hash", self.api_hash_var, 2)
		self.phone_entry = self._secret_entry(card, "Telefono", self.phone_var, 3)
		self.telegram_code_var = tk.StringVar()
		self.telegram_code_entry = self._secret_entry(card, "Codigo Telegram (si lo solicita)", self.telegram_code_var, 4)
		ttk.Button(card, text="Enviar codigo", command=self._send_telegram_code).grid(
			row=4, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		ttk.Checkbutton(
			card,
			text="Mostrar credenciales",
			variable=self.show_credentials_var,
			command=self._toggle_credentials_visibility,
		).grid(row=5, column=1, sticky="w", padx=(10, 0), pady=(12, 0))
		ttk.Button(card, text="Abrir pagina de Telegram", command=lambda: webbrowser.open(TELEGRAM_APPS_URL)).grid(
			row=6, column=0, sticky="w", pady=(14, 0)
		)
		ttk.Button(card, text="Autorizar sesion", command=self._run_login).grid(
			row=6, column=1, sticky="w", padx=(10, 0), pady=(14, 0)
		)
		ttk.Button(card, text="Guardar configuracion", command=self._save_config).grid(
			row=6, column=2, sticky="e", pady=(14, 0)
		)

		help_card = self._card(tab, "Como obtener api_id y api_hash", 0, 1)
		steps = (
			"1. Pulsa Abrir pagina de Telegram.\n"
			"2. Inicia sesion con tu telefono.\n"
			"3. Entra en API development tools.\n"
			"4. Crea una app si no existe.\n"
			"5. Copia api_id y api_hash.\n"
			"6. Guarda esta configuracion.\n\n"
			"El telefono debe incluir prefijo internacional,\n"
			"por ejemplo +34123456789.\n\n"
			"No compartas config/config.ini."
		)
		ttk.Label(help_card, text=steps, style="Card.TLabel", justify="left", wraplength=420).grid(
			row=1, column=0, sticky="nw"
		)
		ttk.Label(
			help_card,
			text=TELEGRAM_APPS_URL,
			style="Card.TLabel",
			foreground="#255a8f",
			wraplength=420,
		).grid(row=2, column=0, sticky="nw", pady=(16, 0))

	def _build_capture_tab(self):
		tab = ttk.Frame(self.tabs, padding=10)
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)
		self.tabs.add(tab, text="Captura")

		channel_card = self._card(tab, "Descargar un canal", 0, 0)
		self.channel_var = tk.StringVar()
		self.max_msgs_var = tk.StringVar()
		self._entry(channel_card, "Canal", self.channel_var, 1)
		ttk.Button(channel_card, text="Descargar", command=self._run_download_channel).grid(
			row=1, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		self._entry(channel_card, "Max mensajes (vacio = sin limite)", self.max_msgs_var, 2)

		dataset_card = self._card(tab, "Crear dataset desde lista", 0, 1)
		self.dataset_name_var = tk.StringVar()
		self.channel_list_var = tk.StringVar()
		self.dataset_max_msgs_var = tk.StringVar()
		self._entry(dataset_card, "Dataset", self.dataset_name_var, 1)
		ttk.Button(dataset_card, text="Crear", command=self._run_build_dataset).grid(
			row=1, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		self._entry(dataset_card, "Lista de canales", self.channel_list_var, 2)
		ttk.Button(dataset_card, text="Elegir archivo", command=lambda: self._choose_file(self.channel_list_var)).grid(
			row=2, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		self._entry(dataset_card, "Max mensajes (vacio = sin limite)", self.dataset_max_msgs_var, 3)

		snowball_card = self._card(tab, "Crear dataset snowball", 1, 0, 2)
		self.snowball_root_var = tk.StringVar()
		self.snowball_dataset_var = tk.StringVar()
		self.snowball_max_msgs_var = tk.StringVar()
		self._entry(snowball_card, "Canal raiz descargado", self.snowball_root_var, 1)
		ttk.Button(snowball_card, text="Generar snowball", command=self._run_snowball_dataset).grid(
			row=1, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		self._entry(snowball_card, "Dataset salida", self.snowball_dataset_var, 2)
		self._entry(snowball_card, "Max mensajes (vacio = sin limite)", self.snowball_max_msgs_var, 3)
		ttk.Label(
			snowball_card,
			text="Usa data/<canal>/related_channels.csv generado al descargar el canal raiz.",
			style="Card.TLabel",
		).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))

	def _build_search_tab(self):
		tab = ttk.Frame(self.tabs, padding=10)
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)
		self.tabs.add(tab, text="Buscar por termino")

		search_card = self._card(tab, "Buscar mensajes por terminos", 0, 0, 2)
		self.search_terms_var = tk.StringVar()
		self.search_dataset_var = tk.StringVar()
		self.search_list_var = tk.StringVar()
		self._entry(search_card, "Nombre del dataset", self.search_dataset_var, 1)
		self._entry(search_card, "Terminos", self.search_terms_var, 2)
		self._entry(search_card, "Lista de canales", self.search_list_var, 3)
		ttk.Button(search_card, text="Elegir archivo", command=lambda: self._choose_file(self.search_list_var)).grid(
			row=3, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		ttk.Button(search_card, text="Buscar", command=self._run_search).grid(
			row=4, column=2, sticky="ew", padx=(8, 0), pady=(12, 0)
		)

		guide_card = self._card(tab, "Como escribir terminos", 1, 0, 2)
		text = (
			"Puedes separar terminos con comas o con OR.\n"
			"Ejemplos: bitcoin, paypal  |  \"frase exacta\" OR transferencia\n"
			"La busqueda se ejecuta en tiempo real sobre la lista de canales seleccionada."
		)
		ttk.Label(guide_card, text=text, style="Card.TLabel", justify="left").grid(row=1, column=0, sticky="w")

	def _build_analysis_tab(self):
		tab = ttk.Frame(self.tabs, padding=10)
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)
		self.tabs.add(tab, text="Analisis")

		charts_card = self._card(tab, "Graficos y dashboard", 0, 0)
		self.analysis_name_var = tk.StringVar()
		self._entry(charts_card, "Canal o dataset", self.analysis_name_var, 1)
		ttk.Button(charts_card, text="Graficos", command=self._run_charts).grid(
			row=1, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		ttk.Button(charts_card, text="Dashboard", command=self._run_dashboard).grid(
			row=2, column=2, sticky="ew", padx=(8, 0), pady=5
		)

		ioc_card = self._card(tab, "IOCs de metodos de pago", 0, 1)
		self.ioc_name_var = tk.StringVar()
		self.ioc_mode_var = tk.StringVar(value="dataset")
		self._entry(ioc_card, "Nombre", self.ioc_name_var, 1)
		ttk.Button(ioc_card, text="Buscar IOCs", command=self._run_iocs).grid(
			row=1, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		ttk.Radiobutton(ioc_card, text="Dataset", variable=self.ioc_mode_var, value="dataset").grid(row=2, column=0, sticky="w")
		ttk.Radiobutton(ioc_card, text="Canal", variable=self.ioc_mode_var, value="channel").grid(row=2, column=1, sticky="w")

		net_card = self._card(tab, "Red de forwards", 1, 0, 2)
		self.net_dataset_var = tk.StringVar()
		self._entry(net_card, "Dataset", self.net_dataset_var, 1)
		ttk.Button(net_card, text="Generar GEXF", command=self._run_net).grid(
			row=1, column=2, sticky="ew", padx=(8, 0), pady=5
		)

	def _build_network_tab(self):
		tab = ttk.Frame(self.tabs, padding=10)
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)
		self.tabs.add(tab, text="Canales similares")

		sim_card = self._card(tab, "Descubrir canales similares", 0, 0, 2)
		self.sim_channel_var = tk.StringVar()
		self.sim_dataset_var = tk.StringVar()
		self.sim_depth_var = tk.StringVar(value="1")
		self.sim_max_var = tk.StringVar()
		self._entry(sim_card, "Canal semilla", self.sim_channel_var, 1)
		ttk.Button(sim_card, text="Descubrir", command=self._run_similar).grid(
			row=1, column=2, sticky="ew", padx=(8, 0), pady=5
		)
		self._entry(sim_card, "Dataset salida", self.sim_dataset_var, 2)
		self._entry(sim_card, "Profundidad", self.sim_depth_var, 3)
		self._entry(sim_card, "Max recomendaciones", self.sim_max_var, 4)

		guide_card = self._card(tab, "Salida generada", 1, 0, 2)
		text = (
			"La red se guarda en dataset/<nombre>/ como CSV, GEXF y GraphML.\n"
			"Puedes abrir channel_recommendations.gexf en Gephi u otra herramienta de redes."
		)
		ttk.Label(guide_card, text=text, style="Card.TLabel", justify="left").grid(row=1, column=0, sticky="w")

	def _load_config(self):
		if not CONFIG_PATH.exists():
			return
		config = configparser.ConfigParser()
		config.read(CONFIG_PATH, encoding="utf-8")
		if "Telegram API credentials" not in config:
			return
		section = config["Telegram API credentials"]
		self.api_id_var.set(section.get("api_id", ""))
		self.api_hash_var.set(section.get("api_hash", ""))
		self.phone_var.set(section.get("phone", ""))
		self.show_credentials_var.set(False)
		self.after(0, self._toggle_credentials_visibility)

	def _toggle_credentials_visibility(self):
		show_char = "" if self.show_credentials_var.get() else "*"
		for entry in (self.api_id_entry, self.api_hash_entry, self.phone_entry):
			entry.configure(show=show_char)

	def _save_config(self):
		api_id = self.api_id_var.get().strip()
		api_hash = self.api_hash_var.get().strip()
		phone = self.phone_var.get().strip()
		if not api_id.isdigit():
			messagebox.showerror("Dato incorrecto", "api_id debe ser numerico.")
			return
		if not api_hash or not phone:
			messagebox.showerror("Faltan datos", "api_hash y telefono son obligatorios.")
			return
		CONFIG_PATH.parent.mkdir(exist_ok=True)
		config = configparser.ConfigParser()
		config["Telegram API credentials"] = {"api_id": api_id, "api_hash": api_hash, "phone": phone}
		with CONFIG_PATH.open("w", encoding="utf-8") as file:
			config.write(file)
		(ROOT / "data").mkdir(exist_ok=True)
		(ROOT / "dataset").mkdir(exist_ok=True)
		messagebox.showinfo("Configuracion", "Configuracion guardada correctamente.")

	def _choose_file(self, variable):
		path = filedialog.askopenfilename(initialdir=ROOT)
		if path:
			variable.set(path)

	def _script(self, name):
		return str(SCRIPTS_DIR / name)

	def _run(self, args):
		if self.running_process is not None:
			messagebox.showwarning("Proceso en marcha", "Ya hay un proceso ejecutandose.")
			return
		self._append_console("> " + " ".join(args) + "\n")
		self.status_var.set("Ejecutando...")
		thread = threading.Thread(target=self._run_worker, args=(args,), daemon=True)
		thread.start()

	def _run_worker(self, args):
		try:
			self.running_process = subprocess.Popen(
				args,
				cwd=ROOT,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				stdin=subprocess.PIPE,
				text=True,
				encoding="utf-8",
				errors="replace",
				creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
			)
			for line in self.running_process.stdout:
				self.output_queue.put(line)
			code = self.running_process.wait()
			self.output_queue.put(f"\n[Proceso terminado con codigo {code}]\n")
		except Exception as exc:
			self.output_queue.put(f"\n[Error: {exc}]\n")
		finally:
			self.running_process = None
			self.output_queue.put(("STATUS", "Listo"))

	def _poll_output(self):
		try:
			while True:
				item = self.output_queue.get_nowait()
				if isinstance(item, tuple) and item[0] == "STATUS":
					self.status_var.set(item[1])
				else:
					self._append_console(item)
		except queue.Empty:
			pass
		self.after(120, self._poll_output)

	def _append_console(self, text):
		self.console.insert(tk.END, text)
		self.console.see(tk.END)

	def _clear_console(self):
		self.console.delete("1.0", tk.END)

	def _send_process_input(self):
		value = self.process_input_var.get()
		self._send_value_to_process(value, clear_var=self.process_input_var)

	def _send_telegram_code(self):
		value = self.telegram_code_var.get().strip()
		if not value:
			messagebox.showinfo("Codigo vacio", "Introduce el codigo recibido en Telegram.")
			return
		self._send_value_to_process(value, clear_var=self.telegram_code_var)

	def _send_value_to_process(self, value, clear_var=None):
		if self.running_process is None or self.running_process.stdin is None:
			messagebox.showinfo("Sin proceso", "No hay ningun proceso esperando entrada.")
			return
		try:
			self.running_process.stdin.write(value + "\n")
			self.running_process.stdin.flush()
			self._append_console("[entrada enviada]\n")
			if clear_var is not None:
				clear_var.set("")
		except Exception as exc:
			messagebox.showerror("Entrada no enviada", str(exc))

	def _stop_process(self):
		if self.running_process is None:
			return
		try:
			if os.name == "nt":
				subprocess.run(
					["taskkill", "/PID", str(self.running_process.pid), "/T", "/F"],
					stdout=subprocess.DEVNULL,
					stderr=subprocess.DEVNULL,
					check=False,
				)
			else:
				self.running_process.terminate()
			self._append_console("\n[Proceso detenido por el usuario]\n")
		except Exception as exc:
			messagebox.showerror("No se pudo detener", str(exc))

	def _require(self, value, label):
		value = value.strip()
		if not value:
			messagebox.showerror("Falta informacion", f"Completa el campo: {label}")
			return None
		return value

	def _run_download_channel(self):
		channel = self._require(self.channel_var.get(), "Canal")
		if not channel:
			return
		args = [sys.executable, self._script("main.py"), "--telegram-channel", channel]
		max_msgs = self.max_msgs_var.get().strip()
		if max_msgs:
			args += ["--max-msgs", max_msgs]
		self._run(args)

	def _run_login(self):
		self._run([sys.executable, self._script("login.py")])

	def _run_build_dataset(self):
		name = self._require(self.dataset_name_var.get(), "Dataset")
		channel_list = self._require(self.channel_list_var.get(), "Lista de canales")
		if not name or not channel_list:
			return
		args = [sys.executable, self._script("build-dataset.py"), "--dataset-name", name, "--channel-list", channel_list]
		max_msgs = self.dataset_max_msgs_var.get().strip()
		if max_msgs:
			args += ["--max-msgs", max_msgs]
		self._run(args)

	def _run_snowball_dataset(self):
		root_channel = self._require(self.snowball_root_var.get(), "Canal raiz descargado")
		if not root_channel:
			return
		channel_list = ROOT / "data" / root_channel / "related_channels.csv"
		if not channel_list.exists():
			messagebox.showerror(
				"No existe related_channels.csv",
				f"Primero descarga el canal {root_channel} para generar {channel_list}",
			)
			return
		dataset_name = self.snowball_dataset_var.get().strip() or f"{root_channel}_n2"
		args = [
			sys.executable,
			self._script("build-dataset.py"),
			"--dataset-name",
			dataset_name,
			"--channel-list",
			str(channel_list),
		]
		max_msgs = self.snowball_max_msgs_var.get().strip()
		if max_msgs:
			args += ["--max-msgs", max_msgs]
		self._run(args)

	def _run_search(self):
		dataset_name = self._require(self.search_dataset_var.get(), "Nombre del dataset")
		terms = self._require(self.search_terms_var.get(), "Terminos")
		channel_list = self._require(self.search_list_var.get(), "Lista de canales")
		if not dataset_name or not terms or not channel_list:
			return
		self._run([
			sys.executable,
			self._script("search_messages.py"),
			"--terms",
			terms,
			"--dataset-name",
			dataset_name,
			"--channel-list",
			channel_list,
		])

	def _run_charts(self):
		name = self._require(self.analysis_name_var.get(), "Canal o dataset")
		if not name:
			return
		if (ROOT / "data" / name).exists():
			self._run([sys.executable, self._script("draw_charts.py"), "--channel", name])
		else:
			self._run([sys.executable, self._script("draw_charts.py"), "--dataset", name])

	def _run_dashboard(self):
		name = self._require(self.analysis_name_var.get(), "Canal o dataset")
		if name:
			self._run([sys.executable, self._script("dashboard.py"), name])

	def _run_iocs(self):
		name = self._require(self.ioc_name_var.get(), "Nombre")
		if not name:
			return
		flag = "--dataset" if self.ioc_mode_var.get() == "dataset" else "--channel"
		self._run([sys.executable, self._script("filtrobtc.py"), flag, name])

	def _run_net(self):
		name = self._require(self.net_dataset_var.get(), "Dataset")
		if name:
			self._run([sys.executable, self._script("net.py"), "--dataset", name])

	def _run_similar(self):
		channel = self._require(self.sim_channel_var.get(), "Canal semilla")
		if not channel:
			return
		args = [sys.executable, self._script("similar_channels.py"), "--telegram-channel", channel]
		dataset = self.sim_dataset_var.get().strip()
		depth = self.sim_depth_var.get().strip()
		max_rec = self.sim_max_var.get().strip()
		if dataset:
			args += ["--dataset-name", dataset]
		if depth:
			args += ["--profundidad", depth]
		if max_rec:
			args += ["--max-recomendaciones", max_rec]
		self._run(args)


def main():
	app = TrackerApp()
	app.mainloop()


if __name__ == "__main__":
	main()
