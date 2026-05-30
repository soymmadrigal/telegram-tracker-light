# -*- coding: utf-8 -*-

import configparser
import getpass
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "config.ini"
CONFIG_EXAMPLE_PATH = CONFIG_DIR / "config.example.ini"
TELEGRAM_APPS_URL = "https://my.telegram.org/auth?to=apps"


def ask_required(prompt, current=None, secret=False):
	while True:
		suffix = f" [{current}]" if current else ""
		if secret:
			value = getpass.getpass(f"{prompt}{suffix}: ").strip()
		else:
			value = input(f"{prompt}{suffix}: ").strip()
		if value:
			return value
		if current:
			return current
		print("Este campo es obligatorio.")


def load_existing_config():
	config = configparser.ConfigParser()
	if CONFIG_PATH.exists():
		config.read(CONFIG_PATH, encoding="utf-8")
	return config


def get_existing_value(config, key):
	try:
		value = config["Telegram API credentials"].get(key, "").strip()
		if value and not value.upper().startswith("TU_"):
			return value
	except KeyError:
		pass
	return None


def validate_api_id(api_id):
	try:
		int(api_id)
		return True
	except ValueError:
		return False


def write_config(api_id, api_hash, phone):
	CONFIG_DIR.mkdir(parents=True, exist_ok=True)
	config = configparser.ConfigParser()
	config["Telegram API credentials"] = {
		"api_id": str(api_id),
		"api_hash": api_hash,
		"phone": phone,
	}
	with CONFIG_PATH.open("w", encoding="utf-8") as file:
		config.write(file)


def write_example_config():
	CONFIG_DIR.mkdir(parents=True, exist_ok=True)
	if CONFIG_EXAMPLE_PATH.exists():
		return
	example = configparser.ConfigParser()
	example["Telegram API credentials"] = {
		"api_id": "TU_API_ID",
		"api_hash": "TU_API_HASH",
		"phone": "+34123456789",
	}
	with CONFIG_EXAMPLE_PATH.open("w", encoding="utf-8") as file:
		example.write(file)


def ensure_project_dirs():
	for folder in ("data", "dataset"):
		Path(folder).mkdir(exist_ok=True)


def print_intro():
	print("")
	print("========================================")
	print("Configuracion inicial de Telegram Tracker")
	print("========================================")
	print("")
	print("Necesitas credenciales de una app de Telegram:")
	print(f"  {TELEGRAM_APPS_URL}")
	print("")
	print("Pasos en Telegram:")
	print("  1. Entra con tu cuenta.")
	print("  2. Abre API development tools.")
	print("  3. Crea una app si no existe.")
	print("  4. Copia api_id y api_hash.")
	print("")
	print("El telefono debe incluir prefijo internacional, por ejemplo +34123456789.")
	print("Estos datos se guardaran localmente en config/config.ini.")
	print("")


def main():
	print_intro()
	write_example_config()
	ensure_project_dirs()

	existing = load_existing_config()
	current_api_id = get_existing_value(existing, "api_id")
	current_api_hash = get_existing_value(existing, "api_hash")
	current_phone = get_existing_value(existing, "phone")

	if CONFIG_PATH.exists():
		print(f"Ya existe {CONFIG_PATH}. Pulsa Enter para conservar valores actuales.")
		print("")

	while True:
		api_id = ask_required("api_id", current=current_api_id)
		if validate_api_id(api_id):
			break
		print("api_id debe ser numerico.")

	api_hash = ask_required("api_hash", current=current_api_hash, secret=True)
	phone = ask_required("Telefono con prefijo internacional", current=current_phone)

	write_config(api_id, api_hash, phone)

	print("")
	print(f"Configuracion guardada en {CONFIG_PATH}")
	print(f"Plantilla de ejemplo disponible en {CONFIG_EXAMPLE_PATH}")
	print("Carpetas data/ y dataset/ listas.")
	print("")
	print("Siguiente paso recomendado:")
	print(f"  {Path(sys.executable).name} menu.py")


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		print("\nConfiguracion cancelada.")
		sys.exit(1)
