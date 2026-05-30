# -*- coding: utf-8 -*-

import argparse
import csv
import os
import re
from pathlib import Path


IOC_PATTERNS = {
	'BTC': re.compile(r'\b(?:bc1[ac-hj-np-z02-9]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b'),
	'ETH_EVM': re.compile(r'\b0x[a-fA-F0-9]{40}\b'),
	'TRON_USDT': re.compile(r'\bT[1-9A-HJ-NP-Za-km-z]{33}\b'),
	'LTC': re.compile(r'\b(?:ltc1[ac-hj-np-z02-9]{11,71}|[LM3][a-km-zA-HJ-NP-Z1-9]{26,33})\b'),
	'BCH': re.compile(r'\b(?:bitcoincash:)?q[0-9a-z]{41}\b', re.IGNORECASE),
	'XMR': re.compile(r'\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b'),
	'IBAN': re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b'),
	'PAYPAL_EMAIL': re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'),
	'BIZUM_PHONE_ES': re.compile(r'(?<!\d)(?:\+34\s*)?[6789]\d(?:[\s.-]?\d{3}){2}(?!\d)'),
}

PAYMENT_CONTEXT = re.compile(
	r'\b(paypal|bizum|iban|btc|bitcoin|eth|ethereum|usdt|tron|trc20|erc20|wallet|monedero|donaci[oó]n|donar|pago|transferencia)\b',
	re.IGNORECASE,
)


def detectar_iocs(message):
	text = message or ""
	results = []
	for ioc_type, pattern in IOC_PATTERNS.items():
		for match in pattern.finditer(text):
			value = match.group().strip()
			if ioc_type in {'PAYPAL_EMAIL', 'BIZUM_PHONE_ES'} and not PAYMENT_CONTEXT.search(text):
				continue
			results.append((ioc_type, value))
	return results


def resolve_input(args):
	if args.input:
		return Path(args.input)
	if args.channel:
		return Path(args.data_base) / args.channel / 'msgs_dataset.csv'
	if args.dataset:
		return Path(args.dataset_base) / args.dataset / 'msgs_dataset.csv'
	raise ValueError('Usa --input, --channel o --dataset.')


def default_output(input_path, args):
	if args.output:
		return Path(args.output)
	return input_path.parent / 'payment_iocs.csv'


def get(row, *names):
	for name in names:
		if name in row and row[name] not in (None, ''):
			return row[name]
	return ''


def procesar_csv(input_file, output_file):
	results = []
	with open(input_file, 'r', encoding='utf-8', errors='replace', newline='') as csvfile:
		reader = csv.DictReader(csvfile)
		for row in reader:
			message = get(row, 'message', 'text')
			for ioc_type, value in detectar_iocs(message):
				results.append({
					'channel_name': get(row, 'channel_name', 'username'),
					'channel_id': get(row, 'channel_id'),
					'msg_id': get(row, 'msg_id'),
					'msg_link': get(row, 'msg_link'),
					'date': get(row, 'date'),
					'ioc_type': ioc_type,
					'ioc_value': value,
					'message': message,
					'views': get(row, 'views'),
					'number_replies': get(row, 'number_replies'),
					'number_forwards': get(row, 'number_forwards'),
					'is_forward': get(row, 'is_forward'),
					'forward_msg_from_peer_name': get(row, 'forward_msg_from_peer_name', 'from_username', 'from_channel_name'),
					'forward_msg_link': get(row, 'forward_msg_link'),
					'is_reply': get(row, 'is_reply'),
					'url': get(row, 'url', 'links'),
					'domain': get(row, 'domain', 'domains'),
				})
				print(f'Encontrado {ioc_type}: {value} en {get(row, "msg_link")}')

	output_file.parent.mkdir(parents=True, exist_ok=True)
	fieldnames = [
		'channel_name',
		'channel_id',
		'msg_id',
		'msg_link',
		'date',
		'ioc_type',
		'ioc_value',
		'message',
		'views',
		'number_replies',
		'number_forwards',
		'is_forward',
		'forward_msg_from_peer_name',
		'forward_msg_link',
		'is_reply',
		'url',
		'domain',
	]
	with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
		writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(results)
	return len(results)


def parse_args():
	parser = argparse.ArgumentParser(description='Busca IOCs de metodos de pago en msgs_dataset.csv.')
	parser.add_argument('--input', help='CSV concreto a procesar.')
	parser.add_argument('--channel', help='Nombre de canal en ./data/<canal>.')
	parser.add_argument('--dataset', help='Nombre de dataset en ./dataset/<dataset>.')
	parser.add_argument('--output', help='CSV de salida. Default: payment_iocs.csv junto al origen.')
	parser.add_argument('--data-base', default='./data', help='Carpeta data.')
	parser.add_argument('--dataset-base', default='./dataset', help='Carpeta dataset.')
	return parser.parse_args()


def main():
	args = parse_args()
	input_file = resolve_input(args)
	if not input_file.exists():
		raise FileNotFoundError(f'No existe {input_file}')
	output_file = default_output(input_file, args)
	count = procesar_csv(input_file, output_file)
	print(f'Resultados guardados en {output_file} ({count} coincidencias)')


if __name__ == '__main__':
	main()
