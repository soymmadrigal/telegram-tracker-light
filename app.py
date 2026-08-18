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
from tkinter import filedialog, messagebox

import customtkinter as ctk


ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
CONFIG_PATH = ROOT / "config" / "config.ini"
TELEGRAM_APPS_URL = "https://my.telegram.org/auth?to=apps"


class TrackerApp(ctk.CTk):
	def __init__(self):
		super().__init__()
		ctk.set_appearance_mode("light")
		ctk.set_default_color_theme("blue")
		ctk.set_widget_scaling(1.06)
		self.title("Telegram Tracker Light")
		self.geometry("1400x900")
		self.minsize(1240, 800)
		self.output_queue = queue.Queue()
		self.running_process = None
		# Guardia SINCRONA contra doble lanzamiento: se marca en _run (hilo de la
		# GUI) antes de arrancar el worker, para que un segundo clic no cuele un
		# segundo proceso. (running_process se asigna despues, dentro del hilo.)
		self._process_active = False
		# Estado para pintar las barras de progreso (tqdm usa '\r') en una sola
		# linea de la consola en vez de acumular una linea por refresco.
		self._progress_active = False
		self._build_layout()
		self._load_config()
		self._poll_output()

	def _build_layout(self):
		self.configure(fg_color="#f4f7fb")
		self.columnconfigure(0, weight=1)
		self.rowconfigure(1, weight=1)
		self.rowconfigure(2, weight=0)

		header = ctk.CTkFrame(self, fg_color="transparent")
		header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 8))
		header.columnconfigure(0, weight=1)
		ctk.CTkLabel(
			header,
			text="Telegram Tracker Light",
			font=ctk.CTkFont("Segoe UI", 29, "bold"),
			text_color="#111827",
		).grid(row=0, column=0, sticky="w")
		ctk.CTkLabel(
			header,
			text="Panel local para configurar, capturar, buscar y analizar canales de Telegram.",
			font=ctk.CTkFont("Segoe UI", 15),
			text_color="#607086",
		).grid(row=1, column=0, sticky="w", pady=(4, 0))
		self.status_var = tk.StringVar(value="Listo")
		self.status_badge = ctk.CTkLabel(
			header,
			textvariable=self.status_var,
			height=34,
			corner_radius=17,
			fg_color="#e6f4ff",
			text_color="#075985",
			font=ctk.CTkFont("Segoe UI", 13, "bold"),
			padx=16,
		)
		self.status_badge.grid(row=0, column=1, sticky="e")

		self.tabs = ctk.CTkTabview(
			self,
			fg_color="#ffffff",
			segmented_button_fg_color="#e5ebf3",
			segmented_button_selected_color="#0f766e",
			segmented_button_selected_hover_color="#115e59",
			segmented_button_unselected_color="#e5ebf3",
			segmented_button_unselected_hover_color="#d6dee9",
			text_color="#111827",
			corner_radius=12,
		)
		self.tabs.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 12))

		self._build_setup_tab()
		self._build_capture_tab()
		self._build_search_tab()
		self._build_analysis_tab()
		self._build_network_tab()

		console_frame = ctk.CTkFrame(self, fg_color="#ffffff", corner_radius=12)
		console_frame.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 18))
		console_frame.rowconfigure(1, weight=1)
		console_frame.columnconfigure(0, weight=1)
		toolbar = ctk.CTkFrame(console_frame, fg_color="transparent")
		toolbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
		ctk.CTkLabel(toolbar, text="Salida de ejecucion", font=ctk.CTkFont("Segoe UI", 15, "bold"), text_color="#111827").pack(side=tk.LEFT)
		ctk.CTkButton(toolbar, text="Limpiar", width=110, height=36, font=ctk.CTkFont("Segoe UI", 14, "bold"), command=self._clear_console).pack(side=tk.RIGHT)
		ctk.CTkButton(toolbar, text="Detener", width=110, height=36, font=ctk.CTkFont("Segoe UI", 14, "bold"), fg_color="#dc2626", hover_color="#b91c1c", command=self._stop_process).pack(side=tk.RIGHT, padx=(0, 8))
		self.console = ctk.CTkTextbox(
			console_frame,
			height=170,
			wrap="word",
			fg_color="#111827",
			text_color="#e5e7eb",
			font=ctk.CTkFont("Cascadia Mono", 13),
		)
		self.console.grid(row=1, column=0, sticky="nsew", padx=14)
		input_bar = ctk.CTkFrame(console_frame, fg_color="transparent")
		input_bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(10, 14))
		input_bar.columnconfigure(1, weight=1)
		ctk.CTkLabel(input_bar, text="Entrada a consola", font=ctk.CTkFont("Segoe UI", 14), text_color="#334155").grid(row=0, column=0, sticky="w", padx=(0, 8))
		self.process_input_var = tk.StringVar()
		self.process_input_entry = ctk.CTkEntry(input_bar, textvariable=self.process_input_var, height=38, font=ctk.CTkFont("Segoe UI", 14))
		self.process_input_entry.grid(row=0, column=1, sticky="ew")
		self.process_input_entry.bind("<Return>", lambda event: self._send_process_input())
		ctk.CTkButton(input_bar, text="Enviar", width=110, height=38, font=ctk.CTkFont("Segoe UI", 14, "bold"), command=self._send_process_input).grid(row=0, column=2, padx=(8, 0))
		self._polish_controls()

	def _polish_controls(self, parent=None):
		parent = parent or self
		for child in parent.winfo_children():
			if isinstance(child, ctk.CTkButton):
				child.configure(height=38, corner_radius=8, font=ctk.CTkFont("Segoe UI", 14, "bold"))
			elif isinstance(child, ctk.CTkRadioButton):
				child.configure(font=ctk.CTkFont("Segoe UI", 14), radiobutton_width=20, radiobutton_height=20)
			elif isinstance(child, ctk.CTkCheckBox):
				child.configure(font=ctk.CTkFont("Segoe UI", 14), checkbox_width=20, checkbox_height=20)
			elif isinstance(child, ctk.CTkSegmentedButton):
				child.configure(font=ctk.CTkFont("Segoe UI", 14, "bold"))
			self._polish_controls(child)

	def _add_tab(self, name):
		self.tabs.add(name)
		tab = self.tabs.tab(name)
		tab.configure(fg_color="#ffffff")
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)
		return tab

	def _card(self, parent, title, row, column, columnspan=1):
		frame = ctk.CTkFrame(parent, fg_color="#f8fafc", border_color="#d8e1ec", border_width=1, corner_radius=12)
		frame.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=10, pady=10)
		frame.columnconfigure(1, weight=1)
		frame.columnconfigure(2, weight=0)
		ctk.CTkLabel(frame, text=title, font=ctk.CTkFont("Segoe UI", 17, "bold"), text_color="#111827").grid(
			row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(18, 12)
		)
		return frame

	def _entry(self, parent, label, variable, row, show=None):
		ctk.CTkLabel(parent, text=label, font=ctk.CTkFont("Segoe UI", 14), text_color="#334155").grid(row=row, column=0, sticky="w", padx=(18, 0), pady=7)
		entry = ctk.CTkEntry(parent, textvariable=variable, show=show, fg_color="#ffffff", height=38, font=ctk.CTkFont("Segoe UI", 14))
		entry.grid(row=row, column=1, sticky="ew", pady=7, padx=(12, 0))
		return entry

	def _secret_entry(self, parent, label, variable, row):
		return self._entry(parent, label, variable, row, show="*")

	def _build_setup_tab(self):
		tab = self._add_tab("Configuracion")
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)
		tab.rowconfigure(0, weight=1)

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
		ctk.CTkButton(card, text="Enviar codigo", command=self._send_telegram_code).grid(
			row=4, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		ctk.CTkCheckBox(
			card,
			text="Mostrar credenciales",
			variable=self.show_credentials_var,
			command=self._toggle_credentials_visibility,
			text_color="#334155",
		).grid(row=5, column=1, sticky="w", padx=(10, 0), pady=(12, 0))
		ctk.CTkButton(card, text="Abrir pagina de Telegram", command=lambda: webbrowser.open(TELEGRAM_APPS_URL)).grid(
			row=6, column=0, sticky="w", padx=(16, 0), pady=(14, 16)
		)
		ctk.CTkButton(card, text="Autorizar sesion", command=self._run_login).grid(
			row=6, column=1, sticky="w", padx=(10, 0), pady=(14, 16)
		)
		ctk.CTkButton(card, text="Guardar configuracion", command=self._save_config).grid(
			row=6, column=2, sticky="e", padx=(8, 16), pady=(14, 16)
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
		ctk.CTkLabel(help_card, text=steps, justify="left", wraplength=460, text_color="#334155").grid(
			row=1, column=0, sticky="nw", padx=16, pady=(0, 0)
		)
		ctk.CTkLabel(
			help_card,
			text=TELEGRAM_APPS_URL,
			text_color="#075985",
			wraplength=460,
		).grid(row=2, column=0, sticky="nw", padx=16, pady=(16, 16))

	def _build_capture_tab(self):
		tab = self._add_tab("Captura")
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)

		channel_card = self._card(tab, "Descargar un canal", 0, 0)
		self.channel_var = tk.StringVar()
		self.max_msgs_var = tk.StringVar()
		self._entry(channel_card, "Canal", self.channel_var, 1)
		ctk.CTkButton(channel_card, text="Descargar", command=self._run_download_channel).grid(
			row=1, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		self._entry(channel_card, "Max mensajes (vacio = sin limite)", self.max_msgs_var, 2)

		dataset_card = self._card(tab, "Crear dataset desde lista", 0, 1)
		self.dataset_name_var = tk.StringVar()
		self.channel_list_var = tk.StringVar()
		self.dataset_max_msgs_var = tk.StringVar()
		self._entry(dataset_card, "Dataset", self.dataset_name_var, 1)
		ctk.CTkButton(dataset_card, text="Crear", command=self._run_build_dataset).grid(
			row=1, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		self._entry(dataset_card, "Lista de canales", self.channel_list_var, 2)
		ctk.CTkButton(dataset_card, text="Elegir archivo", command=lambda: self._choose_file(self.channel_list_var)).grid(
			row=2, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		self._entry(dataset_card, "Max mensajes (vacio = sin limite)", self.dataset_max_msgs_var, 3)

		snowball_card = self._card(tab, "Crear dataset snowball", 1, 0)
		self.snowball_root_var = tk.StringVar()
		self.snowball_dataset_var = tk.StringVar()
		self.snowball_max_msgs_var = tk.StringVar()
		self._entry(snowball_card, "Canal raiz descargado", self.snowball_root_var, 1)
		ctk.CTkButton(snowball_card, text="Generar snowball", command=self._run_snowball_dataset).grid(
			row=1, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		self._entry(snowball_card, "Dataset salida", self.snowball_dataset_var, 2)
		self._entry(snowball_card, "Max mensajes (vacio = sin limite)", self.snowball_max_msgs_var, 3)
		ctk.CTkLabel(
			snowball_card,
			text="Usa data/<canal>/related_channels.csv generado al descargar el canal raiz.",
			text_color="#52606d",
		).grid(row=4, column=0, columnspan=3, sticky="w", padx=16, pady=(10, 16))

		json_card = self._card(tab, "Importar JSON de Telegram Desktop", 1, 1)
		self.telegram_json_var = tk.StringVar()
		self.telegram_json_link_var = tk.StringVar()
		self._entry(json_card, "Archivo JSON", self.telegram_json_var, 1)
		ctk.CTkButton(json_card, text="Elegir archivo", command=lambda: self._choose_file(self.telegram_json_var)).grid(
			row=1, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		self._entry(json_card, "Enlace del canal", self.telegram_json_link_var, 2)
		ctk.CTkButton(json_card, text="Importar JSON", command=self._run_import_telegram_json).grid(
			row=2, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		ctk.CTkLabel(
			json_card,
			text="Ejemplo: https://t.me/Partido_Popular. La salida se guarda en data/partido_popular.",
			text_color="#52606d",
		).grid(row=3, column=0, columnspan=3, sticky="w", padx=16, pady=(10, 16))

	def _build_search_tab(self):
		tab = self._add_tab("Buscar por termino")
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)

		search_card = self._card(tab, "Buscar mensajes por terminos", 0, 0, 2)
		self.search_terms_var = tk.StringVar()
		self.search_dataset_var = tk.StringVar()
		self.search_list_var = tk.StringVar()
		self._entry(search_card, "Nombre del dataset", self.search_dataset_var, 1)
		self._entry(search_card, "Terminos", self.search_terms_var, 2)
		self._entry(search_card, "Lista de canales", self.search_list_var, 3)
		ctk.CTkButton(search_card, text="Elegir archivo", command=lambda: self._choose_file(self.search_list_var)).grid(
			row=3, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		ctk.CTkButton(search_card, text="Buscar", command=self._run_search).grid(
			row=4, column=2, sticky="ew", padx=(8, 16), pady=(12, 16)
		)

		guide_card = self._card(tab, "Como escribir terminos", 1, 0, 2)
		text = (
			"Puedes separar terminos con comas o con OR.\n"
			"Ejemplos: bitcoin, paypal  |  \"frase exacta\" OR transferencia\n"
			"La busqueda se ejecuta en tiempo real sobre la lista de canales seleccionada."
		)
		ctk.CTkLabel(guide_card, text=text, justify="left", text_color="#334155").grid(row=1, column=0, sticky="w", padx=16, pady=(0, 16))

	def _build_analysis_tab(self):
		tab = self._add_tab("Analisis")
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)

		charts_card = self._card(tab, "Graficos y dashboard", 0, 0)
		self.analysis_name_var = tk.StringVar()
		self.analysis_mode_var = tk.StringVar(value="dataset")
		self.dashboard_focus_label_var = tk.StringVar()
		self.dashboard_focus_terms_var = tk.StringVar()
		self._entry(charts_card, "Nombre", self.analysis_name_var, 1)
		ctk.CTkButton(charts_card, text="Graficos", command=self._run_charts).grid(
			row=1, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		ctk.CTkButton(charts_card, text="Dashboard", command=self._run_dashboard).grid(
			row=2, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		ctk.CTkRadioButton(charts_card, text="Dataset", variable=self.analysis_mode_var, value="dataset", text_color="#334155").grid(row=2, column=0, sticky="w", padx=(16, 0))
		ctk.CTkRadioButton(charts_card, text="Canal", variable=self.analysis_mode_var, value="channel", text_color="#334155").grid(row=2, column=1, sticky="w", padx=(10, 0))
		self._entry(charts_card, "Etiqueta del foco", self.dashboard_focus_label_var, 3)
		self._entry(charts_card, "Terminos del foco", self.dashboard_focus_terms_var, 4)
		ctk.CTkLabel(
			charts_card,
			text="Separa terminos con comas. Ejemplo: inmigracion, vacunas, fraude electoral.",
			text_color="#52606d",
			wraplength=470,
		).grid(row=5, column=0, columnspan=3, sticky="w", padx=16, pady=(8, 16))

		ioc_card = self._card(tab, "IOCs de metodos de pago", 0, 1)
		self.ioc_name_var = tk.StringVar()
		self.ioc_mode_var = tk.StringVar(value="dataset")
		self._entry(ioc_card, "Nombre", self.ioc_name_var, 1)
		ctk.CTkButton(ioc_card, text="Buscar IOCs", command=self._run_iocs).grid(
			row=1, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		ctk.CTkButton(ioc_card, text="Detectar temas", command=self._run_theme_detection).grid(
			row=2, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		ctk.CTkRadioButton(ioc_card, text="Dataset", variable=self.ioc_mode_var, value="dataset", text_color="#334155").grid(row=2, column=0, sticky="w", padx=(16, 0))
		ctk.CTkRadioButton(ioc_card, text="Canal", variable=self.ioc_mode_var, value="channel", text_color="#334155").grid(row=2, column=1, sticky="w", padx=(10, 0))

		net_card = self._card(tab, "Red de forwards", 1, 0, 2)
		self.net_dataset_var = tk.StringVar()
		self._entry(net_card, "Dataset", self.net_dataset_var, 1)
		ctk.CTkButton(net_card, text="Generar GEXF", command=self._run_net).grid(
			row=1, column=2, sticky="ew", padx=(8, 16), pady=6
		)

	def _build_network_tab(self):
		tab = self._add_tab("Canales similares")
		tab.columnconfigure(0, weight=1)
		tab.columnconfigure(1, weight=1)

		sim_card = self._card(tab, "Descubrir canales similares", 0, 0, 2)
		self.sim_channel_var = tk.StringVar()
		self.sim_dataset_var = tk.StringVar()
		self.sim_depth_var = tk.StringVar(value="1")
		self.sim_max_var = tk.StringVar()
		self._entry(sim_card, "Canal semilla", self.sim_channel_var, 1)
		ctk.CTkButton(sim_card, text="Descubrir", command=self._run_similar).grid(
			row=1, column=2, sticky="ew", padx=(8, 16), pady=6
		)
		self._entry(sim_card, "Dataset salida", self.sim_dataset_var, 2)
		self._entry(sim_card, "Profundidad", self.sim_depth_var, 3)
		self._entry(sim_card, "Max recomendaciones", self.sim_max_var, 4)

		guide_card = self._card(tab, "Salida generada", 1, 0, 2)
		text = (
			"La red se guarda en dataset/<nombre>/ como CSV, GEXF y GraphML.\n"
			"Puedes abrir channel_recommendations.gexf en Gephi u otra herramienta de redes."
		)
		ctk.CTkLabel(guide_card, text=text, justify="left", text_color="#334155").grid(row=1, column=0, sticky="w", padx=16, pady=(0, 16))

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

	def _set_launch_buttons_enabled(self, enabled):
		# Deshabilita (gris) los botones de lanzamiento mientras corre un proceso;
		# deja activos los de interaccion (Detener, Enviar, Enviar codigo, Limpiar).
		keep = {"Detener", "Enviar", "Enviar codigo", "Limpiar"}
		state = "normal" if enabled else "disabled"
		def walk(widget):
			for child in widget.winfo_children():
				if isinstance(child, ctk.CTkButton):
					try:
						if child.cget("text") not in keep:
							child.configure(state=state)
					except Exception:
						pass
				walk(child)
		walk(self)

	def _run(self, args):
		if self._process_active:
			messagebox.showwarning("Proceso en marcha", "Ya hay un proceso ejecutandose.")
			return
		# Marca ocupado YA, en el hilo de la GUI, antes de arrancar el worker.
		# Tkinter procesa los clics de uno en uno, asi que un segundo clic vera
		# esto puesto y se rechazara (no se lanza un segundo proceso).
		self._process_active = True
		self._set_launch_buttons_enabled(False)   # botones en gris hasta que termine
		self._append_console("> " + " ".join(args) + "\n")
		self.status_var.set("Ejecutando...")
		thread = threading.Thread(target=self._run_worker, args=(args,), daemon=True)
		thread.start()

	def _run_worker(self, args):
		try:
			self.running_process = subprocess.Popen(
				args,
				cwd=ROOT,
				env={**os.environ, "PYTHONUNBUFFERED": "1"},
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				stdin=subprocess.PIPE,
				text=True,
				encoding="utf-8",
				errors="replace",
				creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
			)
			# Preservar el '\r' (retorno de carro) de las barras de progreso: sin
			# esto, el modo universal-newlines lo convierte en '\n' y cada refresco
			# de tqdm aparece como una linea nueva. Con newline='' se conserva y
			# _append_console puede reescribir la linea en su sitio.
			try:
				self.running_process.stdout.reconfigure(newline="")
			except Exception:
				pass
			for line in self.running_process.stdout:
				self.output_queue.put(line)
			code = self.running_process.wait()
			self.output_queue.put(f"\n[Proceso terminado con codigo {code}]\n")
		except Exception as exc:
			self.output_queue.put(f"\n[Error: {exc}]\n")
		finally:
			self.running_process = None
			self._process_active = False   # libera la guardia (final normal, error o crash)
			self.output_queue.put(("STATUS", "Listo"))

	def _poll_output(self):
		try:
			while True:
				item = self.output_queue.get_nowait()
				if isinstance(item, tuple) and item[0] == "STATUS":
					self.status_var.set(item[1])
					if item[1] == "Listo":
						self._set_launch_buttons_enabled(True)   # rehabilita al terminar
				else:
					self._append_console(item)
		except queue.Empty:
			pass
		self.after(120, self._poll_output)

	def _append_console(self, text):
		if not text:
			return
		# Maneja el retorno de carro '\r' de las barras de progreso (tqdm) para que se
		# actualicen en la MISMA linea. Clave: trata '\r\n' (fin de linea en Windows y
		# el refresco final del close() de tqdm) como "reescribe la linea y cierrala",
		# no como linea nueva. Antes solo miraba '\r', y el cierre de la barra (que
		# acaba en '\r\n') se colaba como una segunda linea -> aparecian dos barras.
		if text.endswith("\r\n"):
			body, commit = text[:-2], True
		elif text.endswith("\n"):
			body, commit = text[:-1], True
		elif text.endswith("\r"):
			body, commit = text[:-1], False
		else:
			body, commit = text, False
		# Si el cuerpo trae '\r' internos, solo vale lo que hay tras el ultimo (la
		# barra se reescribe desde el principio de la linea).
		if "\r" in body:
			body = body.rsplit("\r", 1)[-1]
		# Si venimos pintando una barra, reescribe la linea actual; si no, es normal.
		if self._progress_active:
			self.console.delete("end-1c linestart", "end-1c")
		self.console.insert("end-1c", body)
		if commit:
			self.console.insert("end-1c", "\n")
			self._progress_active = False
		else:
			self._progress_active = True
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

	def _run_import_telegram_json(self):
		json_path = self._require(self.telegram_json_var.get(), "Archivo JSON")
		channel_link = self._require(self.telegram_json_link_var.get(), "Enlace del canal")
		if not json_path or not channel_link:
			return
		self._run([
			sys.executable,
			self._script("import_telegram_json.py"),
			"--json",
			json_path,
			"--channel-link",
			channel_link,
		])

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
		name = self._require(self.analysis_name_var.get(), "Nombre")
		if not name:
			return
		if self.analysis_mode_var.get() == "channel":
			self._run([sys.executable, self._script("draw_charts.py"), "--channel", name])
		else:
			self._run([sys.executable, self._script("draw_charts.py"), "--dataset", name])

	def _run_dashboard(self):
		name = self._require(self.analysis_name_var.get(), "Nombre")
		if not name:
			return
		args = [sys.executable, self._script("dashboard.py"), name]
		if self.analysis_mode_var.get() == "channel":
			args.append("--channel")
		focus_label = self.dashboard_focus_label_var.get().strip()
		focus_terms = self.dashboard_focus_terms_var.get().strip()
		if focus_label:
			args += ["--focus-label", focus_label]
		if focus_terms:
			args += ["--focus-terms", focus_terms]
		self._run(args)

	def _run_iocs(self):
		name = self._require(self.ioc_name_var.get(), "Nombre")
		if not name:
			return
		flag = "--dataset" if self.ioc_mode_var.get() == "dataset" else "--channel"
		self._run([sys.executable, self._script("filtrobtc.py"), flag, name])

	def _run_theme_detection(self):
		name = self._require(self.ioc_name_var.get(), "Nombre")
		if not name:
			return
		flag = "--dataset" if self.ioc_mode_var.get() == "dataset" else "--channel"
		self._run([sys.executable, self._script("detect_themes.py"), flag, name])

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
