# -*- coding: utf-8 -*-

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from utils import chats_dataset_columns, msgs_dataset_columns


URL_RE = re.compile(r"https?://[^\s<>)\"']+|t\.me/[A-Za-z0-9_+./-]+", re.IGNORECASE)


def normalize_channel_ref(value):
	value = (value or "").strip()
	if not value:
		raise ValueError("El enlace del canal es obligatorio.")
	if value.startswith("@"):
		value = value[1:]
	if value.lower().startswith("t.me/"):
		value = "https://" + value
	if value.lower().startswith(("http://", "https://")):
		parsed = urlparse(value)
		parts = [part for part in parsed.path.split("/") if part]
		if parsed.netloc.lower() not in {"t.me", "telegram.me"} or not parts:
			raise ValueError("El enlace debe tener formato https://t.me/nombre_del_canal.")
		value = parts[0]
	value = value.strip().strip("/")
	if not re.fullmatch(r"[A-Za-z0-9_]{3,64}", value):
		raise ValueError("No he podido extraer un username valido del enlace del canal.")
	return value


def output_folder_name(username):
	return username.lower()


def telegram_text_to_plain(value):
	if value is None:
		return ""
	if isinstance(value, str):
		return value
	if isinstance(value, list):
		parts = []
		for item in value:
			if isinstance(item, str):
				parts.append(item)
			elif isinstance(item, dict):
				parts.append(str(item.get("text", "")))
		return "".join(parts)
	return str(value)


def iter_text_entities(value):
	if isinstance(value, list):
		for item in value:
			if isinstance(item, dict):
				yield item


def clean_url(url):
	return (url or "").strip().rstrip(".,;:!?)\"]}'")


def extract_urls(message):
	urls = []
	text = telegram_text_to_plain(message.get("text"))
	for match in URL_RE.findall(text):
		urls.append(clean_url(match))
	for entity in iter_text_entities(message.get("text")):
		entity_text = clean_url(entity.get("text"))
		entity_href = clean_url(entity.get("href"))
		if entity.get("type") in {"link", "text_link"}:
			urls.append(entity_href or entity_text)
		elif entity_text.lower().startswith(("http://", "https://", "t.me/")):
			urls.append(entity_text)
	seen = set()
	result = []
	for url in urls:
		if url and url not in seen:
			seen.add(url)
			result.append(url)
	return result


def domain_from_url(url):
	if not url:
		return None
	normalized = url if url.lower().startswith(("http://", "https://")) else "https://" + url
	domain = urlparse(normalized).netloc.lower()
	return re.sub(r"^www\.", "", domain) or None


def parse_date(value):
	if not value:
		return None
	try:
		return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")
	except ValueError:
		return value


def forwarded_peer_id(value):
	if not value:
		return None
	match = re.search(r"(\d+)$", str(value))
	return match.group(1) if match else value


def chat_row(channel_id, title, username):
	row = {column: None for column in chats_dataset_columns()}
	row.update(
		{
			"_": "Channel",
			"id": channel_id,
			"title": title,
			"creator": False,
			"left": False,
			"broadcast": True,
			"verified": False,
			"megagroup": False,
			"restricted": False,
			"signatures": False,
			"min": False,
			"scam": False,
			"has_link": False,
			"has_geo": False,
			"slowmode_enabled": False,
			"call_active": False,
			"call_not_empty": False,
			"fake": False,
			"gigagroup": False,
			"noforwards": False,
			"join_to_send": False,
			"join_request": False,
			"forum": False,
			"stories_hidden": False,
			"stories_hidden_min": False,
			"stories_unavailable": False,
			"signature_profiles": False,
			"username": username,
			"restriction_reason": [],
			"usernames": [],
		}
	)
	return row


def message_row(message, channel_id, channel_name, username):
	msg_id = message.get("id")
	text = telegram_text_to_plain(message.get("text"))
	urls = extract_urls(message)
	first_url = urls[0] if urls else None
	forward_name = message.get("forwarded_from")
	forward_id = message.get("forwarded_from_id")
	reply_to = message.get("reply_to_message_id")
	row = {column: None for column in msgs_dataset_columns()}
	row.update(
		{
			"signature": f"json_import.user.{username}.post.{msg_id}",
			"channel_id": channel_id,
			"channel_name": username,
			"msg_id": msg_id,
			"message": text,
			"date": parse_date(message.get("date")),
			"msg_link": f"https://t.me/{username}/{msg_id}",
			"msg_from_peer": None,
			"msg_from_id": None,
			"views": 0,
			"number_replies": 0,
			"number_forwards": 0,
			"is_forward": 1 if forward_name or forward_id else 0,
			"forward_msg_from_peer_type": "PeerChannel" if forward_id else None,
			"forward_msg_from_peer_id": forwarded_peer_id(forward_id),
			"forward_msg_from_peer_name": forward_name,
			"forward_msg_date": None,
			"forward_msg_date_string": None,
			"forward_msg_link": None,
			"is_reply": 1 if reply_to else 0,
			"reply_to_msg_id": reply_to,
			"reply_msg_link": f"https://t.me/{username}/{reply_to}" if reply_to else None,
			"has_url": bool(first_url),
			"url": first_url,
			"domain": domain_from_url(first_url),
		}
	)
	return row


def write_csv(path, rows, fieldnames):
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", newline="", encoding="utf-8") as csvfile:
		writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(rows)


def import_json(json_path, channel_ref, output):
	username = normalize_channel_ref(channel_ref)
	folder_name = output_folder_name(username)
	output_folder = Path(output) / folder_name
	output_folder.mkdir(parents=True, exist_ok=True)
	(output_folder / "context").mkdir(exist_ok=True)
	(output_folder / "_exceptions-channels.txt").write_text("", encoding="utf-8")
	(output_folder / "context" / "import_source.txt").write_text(
		"telegram_desktop_json\n",
		encoding="utf-8",
	)

	with Path(json_path).open("r", encoding="utf-8") as file:
		data = json.load(file)

	channel_name = data.get("name") or username
	channel_id = data.get("id")
	messages = data.get("messages", [])
	msg_rows = [
		message_row(message, channel_id, channel_name, username)
		for message in messages
		if message.get("type") == "message"
	]
	write_csv(output_folder / "msgs_dataset.csv", msg_rows, msgs_dataset_columns())

	forward_counter = Counter()
	for message in messages:
		if message.get("type") == "message" and message.get("forwarded_from"):
			forward_counter[(forwarded_peer_id(message.get("forwarded_from_id")), message.get("forwarded_from"))] += 1

	chat_rows = [chat_row(channel_id, channel_name, username)]
	for (peer_id, title), _count in forward_counter.items():
		if peer_id or title:
			chat_rows.append(chat_row(peer_id, title, None))
	write_csv(output_folder / "collected_chats.csv", chat_rows, chats_dataset_columns())
	write_csv(output_folder / "collected_chats_full.csv", chat_rows, chats_dataset_columns())

	with (output_folder / "related_channels.csv").open("w", encoding="utf-8", newline="") as file:
		writer = csv.writer(file)
		for row in chat_rows:
			if row.get("username"):
				writer.writerow([row["username"]])

	counter_rows = [
		{
			"id": channel_id,
			"username": username,
			"counter": 1,
			"from_messages": 0,
			"channel_request": 1,
			"channel_req_targeted_by": {"channels": ["self"]},
			"source": [username],
		}
	]
	for (peer_id, title), count in forward_counter.items():
		counter_rows.append(
			{
				"id": peer_id,
				"username": title,
				"counter": count,
				"from_messages": count,
				"channel_request": 0,
				"channel_req_targeted_by": {"channels": [username]},
				"source": [username],
			}
		)
	write_csv(
		output_folder / "counter.csv",
		counter_rows,
		["id", "username", "counter", "from_messages", "channel_request", "channel_req_targeted_by", "source"],
	)

	context_file = output_folder / "context" / f"{folder_name}_log.csv"
	last_msg = max([row["msg_id"] for row in msg_rows], default=0)
	write_csv(context_file, [{"time_download": datetime.now().ctime(), "last_msg": last_msg, "num_msg": len(msg_rows)}], ["time_download", "last_msg", "num_msg"])
	write_csv(
		output_folder / "context" / "collected_channel_log.csv",
		[{"channel": username, "num_datasets": 1, "datasets": str(output_folder)}],
		["channel", "num_datasets", "datasets"],
	)
	return output_folder, len(msg_rows)


def main():
	parser = argparse.ArgumentParser(description="Importa un JSON exportado por Telegram Desktop como captura local.")
	parser.add_argument("--json", required=True, help="Archivo JSON exportado por Telegram Desktop.")
	parser.add_argument("--channel-link", required=True, help="Enlace del canal. Ejemplo: https://t.me/Partido_Popular")
	parser.add_argument("--output", default="./data", help="Carpeta base de salida. Default: ./data")
	args = parser.parse_args()

	output_folder, num_rows = import_json(args.json, args.channel_link, args.output)
	print(f"Importados {num_rows} mensajes en {output_folder}")


if __name__ == "__main__":
	main()
