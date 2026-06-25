# -*- coding: utf-8 -*-

import argparse
import asyncio
import csv
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
from telethon import errors
from telethon.tl import types

from api import get_connection
from utils import (
	create_dirs,
	get_config_attrs,
	msgs_dataset_columns,
	chats_dataset_columns,
	put_last_download_context,
	store_channels_download,
)


PROGRESS_EVERY = 10
THROTTLE_EVERY_MATCHES = 250
THROTTLE_SLEEP_SECONDS = 0.7
FWD_ENTITY_CACHE = {}


def parse_terms(raw_terms):
	terms = re.split(r',|\s+OR\s+', raw_terms or "", flags=re.IGNORECASE)
	return [term.strip() for term in terms if term.strip()]


def get_optimized_search_queries(search_terms):
	cleaned_terms = []
	for term in search_terms:
		is_exact = term.startswith('"') and term.endswith('"')
		cleaned_terms.append({
			'original': term,
			'query': term.strip('"'),
			'is_exact': is_exact,
		})
	cleaned_terms.sort(key=lambda item: len(item['query']))

	optimized = []
	for item in cleaned_terms:
		is_redundant = False
		for other in optimized:
			if other['query'].lower() in item['query'].lower() and not other['is_exact']:
				is_redundant = True
				break
		if not is_redundant:
			optimized.append(item)
	return optimized, cleaned_terms


def clean_message_text(text):
	return ' '.join((text or "").split()).strip()


def extract_url_attrs(text):
	match = re.search(r'https?://\S+', text or "")
	if not match:
		return 0, None, None
	url = match.group().rstrip('.,);]')
	domain = urlparse(url).netloc
	domain = re.sub(r'^www\.', '', domain, flags=re.IGNORECASE)
	domain = re.sub(r'^(m\.)?youtu\.be$|^m\.youtube\.com$', 'youtube.com', domain)
	domain = 'twitter.com' if domain == 't.co' else domain
	return 1, url, domain


def matches_targets(message_text, targets):
	text = (message_text or "").lower()
	for target in targets:
		query = target['query'].lower()
		if target['is_exact'] and query in text:
			return True
		if not target['is_exact'] and all(word in text for word in query.split()):
			return True
	return False


def empty_message_row(channel_username):
	return {column: None for column in msgs_dataset_columns()} | {
		'channel_name': channel_username,
		'is_forward': 0,
		'is_reply': 0,
		'has_url': 0,
		'views': 0,
		'number_replies': 0,
		'number_forwards': 0,
	}


def peer_attrs(peer):
	if isinstance(peer, types.PeerUser):
		return 'PeerUser', peer.user_id
	if isinstance(peer, types.PeerChat):
		return 'PeerChat', peer.chat_id
	if isinstance(peer, types.PeerChannel):
		return 'PeerChannel', peer.channel_id
	return None, None


async def resolve_fwd_username(client, fwd_from):
	if not fwd_from or not getattr(fwd_from, 'from_id', None):
		return None
	if isinstance(fwd_from.from_id, types.PeerUser):
		return None
	if isinstance(fwd_from.from_id, types.PeerChannel):
		channel_id = fwd_from.from_id.channel_id
		if channel_id in FWD_ENTITY_CACHE:
			return FWD_ENTITY_CACHE[channel_id]
		try:
			entity = await client.get_entity(channel_id)
			username = getattr(entity, 'username', None)
		except Exception:
			username = None
		FWD_ENTITY_CACHE[channel_id] = username
		return username
	return None


async def message_to_dataset_row(client, channel_username, message):
	row = empty_message_row(channel_username)
	msg_id = getattr(message, 'id', None)
	text = clean_message_text(getattr(message, 'message', None) or getattr(message, 'text', None))
	date = getattr(message, 'date', None)
	date_str = date.strftime('%Y-%m-%d %H:%M:%S') if date else None

	row['signature'] = f'search.user.{channel_username}.post.{msg_id}'
	row['channel_id'] = getattr(message, 'chat_id', None)
	row['msg_id'] = msg_id
	row['message'] = text
	row['date'] = date_str
	row['msg_link'] = f'https://t.me/{channel_username}/{msg_id}'

	row['msg_from_peer'], row['msg_from_id'] = peer_attrs(getattr(message, 'from_id', None))
	row['views'] = getattr(message, 'views', None) or 0
	row['number_replies'] = getattr(message, 'replies_count', None) or 0
	row['number_forwards'] = getattr(message, 'forwards', None) or 0

	fwd_from = getattr(message, 'fwd_from', None)
	row['is_forward'] = 1 if fwd_from else 0
	if fwd_from:
		row['forward_msg_from_peer_type'], row['forward_msg_from_peer_id'] = peer_attrs(getattr(fwd_from, 'from_id', None))
		row['forward_msg_from_peer_name'] = await resolve_fwd_username(client, fwd_from)
		forward_date = getattr(fwd_from, 'date', None)
		if forward_date:
			row['forward_msg_date'] = forward_date.strftime('%Y-%m-%d %H:%M:%S')
			row['forward_msg_date_string'] = forward_date.strftime('%Y-%m-%d')
		channel_post = getattr(fwd_from, 'channel_post', None)
		if row['forward_msg_from_peer_name'] and channel_post:
			row['forward_msg_link'] = f"https://t.me/{row['forward_msg_from_peer_name']}/{channel_post}"

	reply_to_msg_id = getattr(message, 'reply_to_msg_id', None)
	row['is_reply'] = 1 if reply_to_msg_id else 0
	row['reply_to_msg_id'] = reply_to_msg_id
	if reply_to_msg_id:
		row['reply_msg_link'] = f'https://t.me/{channel_username}/{reply_to_msg_id}'

	row['has_url'], row['url'], row['domain'] = extract_url_attrs(text)
	return row


def chat_row_from_entity(entity):
	row = {column: None for column in chats_dataset_columns()}
	data = entity.to_dict() if hasattr(entity, 'to_dict') else {}
	for column in chats_dataset_columns():
		if column in data:
			row[column] = data[column]
	row['id'] = getattr(entity, 'id', row.get('id'))
	row['title'] = getattr(entity, 'title', row.get('title'))
	row['username'] = getattr(entity, 'username', row.get('username'))
	row['verified'] = getattr(entity, 'verified', row.get('verified'))
	row['broadcast'] = getattr(entity, 'broadcast', row.get('broadcast'))
	row['megagroup'] = getattr(entity, 'megagroup', row.get('megagroup'))
	row['participants_count'] = getattr(entity, 'participants_count', row.get('participants_count'))
	return row


def append_csv(path, rows, columns):
	if not rows:
		if not os.path.isfile(path):
			pd.DataFrame(columns=columns).to_csv(path, index=False, encoding='utf-8')
		return
	df = pd.DataFrame(rows)
	for column in columns:
		if column not in df.columns:
			df[column] = None
	df = df[columns]
	df.to_csv(path, mode='a', index=False, header=not os.path.isfile(path), encoding='utf-8')


async def search_channel(client, channel_username, terms):
	try:
		entity = await client.get_entity(channel_username)
	except errors.rpcerrorlist.UsernameInvalidError:
		print(f'Canal no valido o inexistente: {channel_username}')
		return None, []
	except Exception as exc:
		print(f'No se pudo abrir {channel_username}: {exc}')
		return None, []

	optimized_queries, targets = get_optimized_search_queries(terms)
	seen_ids = set()
	rows = []

	for search_item in optimized_queries:
		query = search_item['query']
		api_results = 0
		before = len(rows)
		print(f'Buscando "{query}" en {channel_username}')
		try:
			async for message in client.iter_messages(entity, search=query, limit=None):
				api_results += 1
				msg_id = getattr(message, 'id', None)
				if msg_id is None or msg_id in seen_ids:
					continue
				text = getattr(message, 'message', None) or getattr(message, 'text', None) or ""
				if not matches_targets(text, targets):
					continue
				seen_ids.add(msg_id)
				rows.append(await message_to_dataset_row(client, channel_username, message))
				if len(rows) % PROGRESS_EVERY == 0:
					print(f'{channel_username}: {len(rows)} coincidencias unicas')
				if THROTTLE_EVERY_MATCHES and len(rows) % THROTTLE_EVERY_MATCHES == 0:
					await asyncio.sleep(THROTTLE_SLEEP_SECONDS)
		except (errors.rpcerrorlist.FloodWaitError, errors.rpcerrorlist.FloodTestPhoneWaitError) as exc:
			print(f'Flood wait en {channel_username}: esperando {exc.seconds} segundos')
			await asyncio.sleep(exc.seconds)
		print(f'{channel_username}: "{query}" API={api_results}, nuevas={len(rows) - before}')

	return entity, rows


def read_channels(args):
	if args.telegram_channel:
		return [args.telegram_channel.strip().lstrip('@')]
	with open(args.channel_list, 'r', encoding='utf-8') as file:
		return [line.strip().lstrip('@') for line in file if line.strip()]


def parse_args():
	parser = argparse.ArgumentParser(description='Busca mensajes en Telegram y escribe CSV compatible con main.py.')
	parser.add_argument('--terms', required=True, help='Terminos separados por comas u operador OR.')
	parser.add_argument('--telegram-channel', help='Canal unico a buscar.')
	parser.add_argument('--channel-list', help='Archivo con canales, uno por linea.')
	parser.add_argument('--dataset-name', help='Nombre de dataset cuando se busca sobre una lista.')
	parser.add_argument('--output-data', default='./data', help='Carpeta data (default: ./data).')
	parser.add_argument('--output-dataset', default='./dataset', help='Carpeta dataset (default: ./dataset).')
	args = parser.parse_args()
	if not args.telegram_channel and not args.channel_list:
		parser.error('usa --telegram-channel o --channel-list')
	if args.channel_list and not args.dataset_name:
		parser.error('--dataset-name es obligatorio con --channel-list')
	return args


async def main_async():
	args = parse_args()
	terms = parse_terms(args.terms)
	if not terms:
		raise ValueError('No hay terminos de busqueda.')

	config = get_config_attrs()
	client = await get_connection(
		'session_file',
		int(config['api_id']),
		config['api_hash'],
		config['phone'],
	)
	channels = read_channels(args)

	dataset_folder = None
	if args.dataset_name:
		dataset_folder = os.path.join(args.output_dataset, args.dataset_name)
		create_dirs(dataset_folder)
		with open(os.path.join(dataset_folder, 'channel_list.csv'), 'w', encoding='utf-8') as out:
			out.write('\n'.join(channels) + '\n')

	try:
		for channel in channels:
			output_folder = os.path.join(args.output_data, channel)
			create_dirs(output_folder)
			entity, rows = await search_channel(client, channel, terms)
			if entity is None:
				continue

			append_csv(os.path.join(output_folder, 'collected_chats.csv'), [chat_row_from_entity(entity)], chats_dataset_columns())
			append_csv(os.path.join(output_folder, 'msgs_dataset.csv'), rows, msgs_dataset_columns())
			put_last_download_context(
				os.path.join(output_folder, 'context', f'{channel}_search_log.csv'),
				time.ctime(),
				max([row['msg_id'] for row in rows], default=0),
				len(rows),
			)
			store_channels_download(os.path.join(output_folder, 'context', 'collected_channel_log.csv'), channel, output_folder)

			if dataset_folder:
				append_csv(os.path.join(dataset_folder, 'collected_chats.csv'), [chat_row_from_entity(entity)], chats_dataset_columns())
				append_csv(os.path.join(dataset_folder, 'msgs_dataset.csv'), rows, msgs_dataset_columns())
	finally:
		await client.disconnect()

	if dataset_folder and os.path.exists(os.path.join(dataset_folder, 'collected_chats.csv')):
		df = pd.read_csv(os.path.join(dataset_folder, 'collected_chats.csv'), low_memory=False)
		df.drop_duplicates(subset=['id'], keep='last', inplace=True)
		df.to_csv(os.path.join(dataset_folder, 'collected_chats.csv'), index=False, encoding='utf-8')

	print(f'Busqueda finalizada: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')


if __name__ == '__main__':
	asyncio.run(main_async())
