# -*- coding: utf-8 -*-

import argparse
import csv
import re
from pathlib import Path


THEME_PATTERNS = {
	"odio_grupo": [
		r"\b(invasores|plaga|escoria|par[aá]sitos?|ratas?|cucarachas?)\b",
		r"\b(expulsar|echar|deportar|eliminar)\b.{0,60}\b(inmigrantes|musulmanes|jud[ií]os|gitanos|menas|refugiados)\b",
		r"\b(odio|asco)\b.{0,50}\b(inmigrantes|musulmanes|jud[ií]os|gitanos|menas|refugiados)\b",
	],
	"deshumanizacion": [
		r"\b(no son personas|no son humanos|subhumanos|animales|alima[nñ]as)\b",
		r"\b(convertir(?:los|las)? en polvo|barrer(?:los|las)?|limpiar el pa[ií]s)\b",
	],
	"violencia_o_exclusion": [
		r"\b(hay que|debemos|toca)\b.{0,40}\b(colgarlos|fusilarlos|matarlos|aplastarlos|lincharlos)\b",
		r"\b(prohibir|ilegalizar|encerrar)\b.{0,50}\b(a todos|a estas personas|a esos)\b",
	],
	"teoria_conspirativa": [
		r"\b(globalistas?|agenda 2030|nuevo orden mundial|plandemia|gran reemplazo)\b",
		r"\b(nos quieren|quieren)\b.{0,80}\b(controlar|sustituir|reemplazar|esclavizar)\b",
		r"\b(elites?|soros|foro de davos)\b.{0,80}\b(controlan|financian|dirigen)\b",
	],
	"desinformacion_salud_ciencia": [
		r"\b(vacunas?)\b.{0,80}\b(matan|esterilizan|chips?|grafeno|veneno)\b",
		r"\b(covid|coronavirus)\b.{0,80}\b(invento|farsa|montaje|plandemia)\b",
	],
	"fraude_electoral_institucional": [
		r"\b(fraude electoral|pucherazo|voto robado|urnas manipuladas)\b",
		r"\b(jueces|medios|periodistas|prensa)\b.{0,80}\b(comprados|vendidos|manipulados)\b",
	],
	"alarma_desinformativa": [
		r"\b(no quieren que sepas|lo que no te cuentan|despierta|abre los ojos)\b",
		r"\b(comparte antes de que lo borren|censurado por decir la verdad)\b",
	],
}

COMPILED_PATTERNS = {
	theme: [re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in patterns]
	for theme, patterns in THEME_PATTERNS.items()
}


def resolve_input(args):
	if args.input:
		return Path(args.input)
	if args.channel:
		return Path(args.data_base) / args.channel / "msgs_dataset.csv"
	if args.dataset:
		return Path(args.dataset_base) / args.dataset / "msgs_dataset.csv"
	raise ValueError("Usa --input, --channel o --dataset.")


def default_output(input_path, args):
	if args.output:
		return Path(args.output)
	return input_path.parent / "theme_flags.csv"


def get(row, *names):
	for name in names:
		if name in row and row[name] not in (None, ""):
			return row[name]
	return ""


def compact(text):
	return re.sub(r"\s+", " ", text or "").strip()


def detect_themes(message):
	text = compact(message)
	results = []
	for theme, patterns in COMPILED_PATTERNS.items():
		matches = []
		for pattern in patterns:
			for match in pattern.finditer(text):
				matches.append(compact(match.group(0))[:180])
		if matches:
			results.append({
				"theme": theme,
				"score": min(100, 35 + len(matches) * 20),
				"matches": " | ".join(dict.fromkeys(matches)),
			})
	return results


def process_csv(input_file, output_file):
	results = []
	with open(input_file, "r", encoding="utf-8", errors="replace", newline="") as csvfile:
		reader = csv.DictReader(csvfile)
		for row in reader:
			message = get(row, "message", "text")
			for detection in detect_themes(message):
				results.append({
					"channel_name": get(row, "channel_name", "username"),
					"channel_id": get(row, "channel_id"),
					"msg_id": get(row, "msg_id"),
					"msg_link": get(row, "msg_link"),
					"date": get(row, "date"),
					"theme": detection["theme"],
					"score": detection["score"],
					"matched_text": detection["matches"],
					"message": message,
					"views": get(row, "views"),
					"number_replies": get(row, "number_replies"),
					"number_forwards": get(row, "number_forwards"),
					"is_forward": get(row, "is_forward"),
					"forward_msg_from_peer_name": get(row, "forward_msg_from_peer_name"),
					"forward_msg_link": get(row, "forward_msg_link"),
					"url": get(row, "url", "links"),
					"domain": get(row, "domain", "domains"),
				})

	output_file.parent.mkdir(parents=True, exist_ok=True)
	fieldnames = [
		"channel_name",
		"channel_id",
		"msg_id",
		"msg_link",
		"date",
		"theme",
		"score",
		"matched_text",
		"message",
		"views",
		"number_replies",
		"number_forwards",
		"is_forward",
		"forward_msg_from_peer_name",
		"forward_msg_link",
		"url",
		"domain",
	]
	with open(output_file, "w", encoding="utf-8", newline="") as csvfile:
		writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(results)
	return len(results)


def parse_args():
	parser = argparse.ArgumentParser(
		description="Detecta indicios revisables de odio, teorias conspirativas y desinformacion en msgs_dataset.csv."
	)
	parser.add_argument("--input", help="CSV concreto a procesar.")
	parser.add_argument("--channel", help="Nombre de canal en ./data/<canal>.")
	parser.add_argument("--dataset", help="Nombre de dataset en ./dataset/<dataset>.")
	parser.add_argument("--output", help="CSV de salida. Default: theme_flags.csv junto al origen.")
	parser.add_argument("--data-base", default="./data", help="Carpeta data.")
	parser.add_argument("--dataset-base", default="./dataset", help="Carpeta dataset.")
	return parser.parse_args()


def main():
	args = parse_args()
	input_file = resolve_input(args)
	if not input_file.exists():
		raise FileNotFoundError(f"No existe {input_file}")
	output_file = default_output(input_file, args)
	count = process_csv(input_file, output_file)
	print(f"Resultados guardados en {output_file} ({count} indicios)")
	print("Nota: son indicios por reglas, no una clasificacion definitiva. Requieren revision humana.")


if __name__ == "__main__":
	main()
