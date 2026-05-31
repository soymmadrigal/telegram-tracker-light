# -*- coding: utf-8 -*-

import argparse
import csv
import re
from pathlib import Path


IOC_PATTERNS = {
	'BTC': re.compile(r'\b(?:bc1[ac-hj-np-z02-9]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b', re.IGNORECASE),
	'ETH_EVM': re.compile(r'\b0x[a-fA-F0-9]{40}\b'),
	'TRON_USDT': re.compile(r'\bT[1-9A-HJ-NP-Za-km-z]{33}\b'),
	'LTC': re.compile(r'\b(?:ltc1[ac-hj-np-z02-9]{11,71}|[LM3][a-km-zA-HJ-NP-Z1-9]{26,33})\b', re.IGNORECASE),
	'BCH': re.compile(r'\b(?:bitcoincash:)?q[0-9a-z]{41}\b', re.IGNORECASE),
	'XMR': re.compile(r'\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b'),
	'IBAN': re.compile(r'\b[A-Z]{2}\d{2}', re.IGNORECASE),
	'PAYPAL_ME': re.compile(r'https?://(?:www\.)?paypal\.me/[A-Za-z0-9._-]+|paypal\.me/[A-Za-z0-9._-]+', re.IGNORECASE),
	'PAYPAL_EMAIL': re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'),
	'BIZUM_PHONE_ES': re.compile(r'(?<!\d)(?:\+34\s*)?[6789]\d(?:[\s.-]?\d{3}){2}(?!\d)'),
}

CONTEXT_PATTERNS = {
	'BTC': re.compile(r'\b(btc|bitcoin|wallet|monedero|donacion|donacion|donar|pago|pagar|cripto|crypto)\b', re.IGNORECASE),
	'ETH_EVM': re.compile(r'\b(eth|ethereum|evm|erc20|usdt|usdc|wallet|metamask|monedero|donacion|donar|pago|pagar|cripto|crypto)\b', re.IGNORECASE),
	'TRON_USDT': re.compile(r'\b(tron|trx|trc20|usdt|wallet|monedero|donacion|donar|pago|pagar|cripto|crypto)\b', re.IGNORECASE),
	'LTC': re.compile(r'\b(ltc|litecoin|wallet|monedero|donacion|donar|pago|pagar|cripto|crypto)\b', re.IGNORECASE),
	'BCH': re.compile(r'\b(bch|bitcoin cash|bitcoincash|wallet|monedero|donacion|donar|pago|pagar|cripto|crypto)\b', re.IGNORECASE),
	'XMR': re.compile(r'\b(xmr|monero|wallet|monedero|donacion|donar|pago|pagar|cripto|crypto)\b', re.IGNORECASE),
	'IBAN': re.compile(r'\b(iban|transferencia|cuenta bancaria|donacion|donar|pago|pagar|ingreso)\b', re.IGNORECASE),
	'PAYPAL_EMAIL': re.compile(r'\b(paypal|paypal\.me|donar por paypal|pago por paypal|enviar por paypal)\b', re.IGNORECASE),
	'BIZUM_PHONE_ES': re.compile(r'\b(bizum|donar por bizum|pago por bizum|enviar bizum)\b', re.IGNORECASE),
}

EMAIL_EXCLUDE_CONTEXT = re.compile(
	r'\b(contacto|email|correo|prensa|info|soporte|support|newsletter|escribenos|escribenos|contacta|mailto)\b',
	re.IGNORECASE,
)

IBAN_LENGTHS = {
	'AD': 24, 'AE': 23, 'AL': 28, 'AT': 20, 'AZ': 28, 'BA': 20, 'BE': 16, 'BG': 22,
	'BH': 22, 'BR': 29, 'CH': 21, 'CR': 22, 'CY': 28, 'CZ': 24, 'DE': 22, 'DK': 18,
	'DO': 28, 'EE': 20, 'EG': 29, 'ES': 24, 'FI': 18, 'FO': 18, 'FR': 27, 'GB': 22,
	'GE': 22, 'GI': 23, 'GL': 18, 'GR': 27, 'GT': 28, 'HR': 21, 'HU': 28, 'IE': 22,
	'IL': 23, 'IS': 26, 'IT': 27, 'JO': 30, 'KW': 30, 'KZ': 20, 'LB': 28, 'LC': 32,
	'LI': 21, 'LT': 20, 'LU': 20, 'LV': 21, 'MC': 27, 'MD': 24, 'ME': 22, 'MK': 19,
	'MR': 27, 'MT': 31, 'MU': 30, 'NL': 18, 'NO': 15, 'PK': 24, 'PL': 28, 'PS': 29,
	'PT': 25, 'QA': 29, 'RO': 24, 'RS': 22, 'SA': 24, 'SC': 31, 'SE': 24, 'SI': 19,
	'SK': 24, 'SM': 27, 'ST': 25, 'SV': 28, 'TL': 23, 'TN': 24, 'TR': 26, 'UA': 29,
	'VA': 22, 'VG': 24, 'XK': 20,
}


def nearby_text(text, start, end, window=90):
	return text[max(0, start - window): min(len(text), end + window)]


def has_near_context(ioc_type, text, start, end):
	pattern = CONTEXT_PATTERNS.get(ioc_type)
	if pattern is None:
		return True
	return bool(pattern.search(nearby_text(text, start, end)))


def normalize_iban(value):
	return re.sub(r'\s+', '', value).upper()


def valid_iban(value):
	iban = normalize_iban(value)
	if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{11,30}', iban):
		return False
	rearranged = iban[4:] + iban[:4]
	digits = ''.join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
	try:
		return int(digits) % 97 == 1
	except ValueError:
		return False


def iter_iban_matches(text):
	for start in re.finditer(r'\b[A-Z]{2}\d{2}', text, re.IGNORECASE):
		country = start.group()[:2].upper()
		length = IBAN_LENGTHS.get(country)
		if not length:
			continue
		chars = []
		end = start.start()
		pos = start.start()
		while pos < len(text) and len(chars) < length:
			ch = text[pos]
			if ch.isalnum():
				chars.append(ch)
				end = pos + 1
			elif ch in {' ', '\t'}:
				pass
			else:
				break
			pos += 1
		if len(chars) == length:
			value = ''.join(chars)
			if valid_iban(value):
				yield start.start(), end, value


def valid_ioc(ioc_type, value, text, start, end):
	if ioc_type == 'IBAN':
		return valid_iban(value) and has_near_context(ioc_type, text, start, end)
	if ioc_type == 'PAYPAL_EMAIL':
		context = nearby_text(text, start, end)
		if EMAIL_EXCLUDE_CONTEXT.search(context) and not re.search(r'paypal', context, re.IGNORECASE):
			return False
		return has_near_context(ioc_type, text, start, end)
	if ioc_type == 'PAYPAL_ME':
		return True
	if ioc_type == 'BIZUM_PHONE_ES':
		return has_near_context(ioc_type, text, start, end)
	if ioc_type in {'BTC', 'ETH_EVM', 'TRON_USDT', 'LTC', 'BCH', 'XMR'}:
		return has_near_context(ioc_type, text, start, end)
	return True


def detectar_iocs(message):
	text = message or ""
	results = []
	seen = set()
	for start, end, value in iter_iban_matches(text):
		if has_near_context('IBAN', text, start, end):
			key = ('IBAN', value)
			if key not in seen:
				seen.add(key)
				results.append(key)
	for ioc_type, pattern in IOC_PATTERNS.items():
		if ioc_type == 'IBAN':
			continue
		for match in pattern.finditer(text):
			value = match.group().strip()
			if not valid_ioc(ioc_type, value, text, match.start(), match.end()):
				continue
			if ioc_type == 'IBAN':
				value = normalize_iban(value)
			key = (ioc_type, value)
			if key in seen:
				continue
			seen.add(key)
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
