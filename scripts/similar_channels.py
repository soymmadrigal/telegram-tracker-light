# -*- coding: utf-8 -*-

import argparse
import asyncio
import csv
import os
from collections import Counter, deque
from datetime import datetime, timezone

import networkx as nx
import pandas as pd
from telethon import TelegramClient, functions
from telethon.errors.rpcerrorlist import RpcCallFailError

from utils import create_dirs, get_config_attrs, chats_dataset_columns, store_channels_related

try:
	from langdetect import LangDetectException, detect
except Exception:
	LangDetectException = Exception
	detect = None


def chat_row(info):
	row = {column: None for column in chats_dataset_columns()}
	row.update({
		'_': 'Channel',
		'id': info.get('id'),
		'title': info.get('title'),
		'username': info.get('username'),
		'verified': info.get('verified'),
		'participants_count': info.get('participants_count'),
		'date': info.get('date_created'),
		'level': info.get('nivel'),
	})
	return row


async def obtener_canales_similares(cliente, canal):
	try:
		resultado = await cliente(functions.channels.GetChannelRecommendationsRequest(channel=canal))
		return resultado.chats
	except RpcCallFailError as exc:
		print(f'Error de Telegram API al obtener recomendaciones: {exc}')
		return []
	except Exception as exc:
		print(f'Error inesperado al obtener recomendaciones de {canal}: {exc}')
		return []


async def inferir_idioma(cliente, canal_similar):
	lang_code = getattr(canal_similar, 'lang_code', None)
	if lang_code:
		return lang_code
	textos = [getattr(canal_similar, 'title', None) or ""]
	try:
		full = await cliente(functions.channels.GetFullChannelRequest(channel=canal_similar))
		about = getattr(full.full_chat, 'about', None)
		if about:
			textos.append(about)
	except Exception:
		pass
	texto = ' '.join(textos).strip()
	if not texto or detect is None:
		return 'unknown'
	try:
		return detect(texto)
	except (LangDetectException, Exception):
		return 'unknown'


async def crear_grafo(cliente, canal, profundidad_maxima=1, max_recomendaciones=None):
	if profundidad_maxima < 1:
		raise ValueError('La profundidad debe ser >= 1')

	visitados = set()
	en_cola = {canal}
	catalog = {}
	aristas = set()
	eventos = []
	cola = deque([(canal, 0)])
	duplicados_descartados = 0
	sin_username_descartados = 0
	conteo_nivel = Counter()
	paso = 0

	while cola:
		canal_actual, nivel_actual = cola.popleft()
		en_cola.discard(canal_actual)
		if canal_actual in visitados:
			continue
		visitados.add(canal_actual)
		if nivel_actual >= profundidad_maxima:
			continue

		print(f'Buscando similares de {canal_actual} en nivel {nivel_actual + 1}/{profundidad_maxima}')
		canales = await obtener_canales_similares(cliente, canal_actual)
		for i, canal_similar in enumerate(canales):
			if max_recomendaciones is not None and i >= max_recomendaciones:
				break
			username = getattr(canal_similar, 'username', None)
			if not username:
				sin_username_descartados += 1
				continue

			arista = (canal_actual, username)
			if arista not in aristas:
				aristas.add(arista)
				paso += 1
				eventos.append({
					'step': paso,
					'nivel': nivel_actual + 1,
					'source': canal_actual,
					'target': username,
					'discovered_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S%z'),
				})

			if username not in catalog:
				catalog[username] = {
					'id': canal_similar.id,
					'username': username,
					'title': canal_similar.title,
					'verified': canal_similar.verified,
					'participants_count': getattr(canal_similar, 'participants_count', None),
					'date_created': canal_similar.date.strftime('%Y-%m-%d %H:%M:%S') if canal_similar.date else None,
					'language': await inferir_idioma(cliente, canal_similar),
					'nivel': nivel_actual + 1,
				}
				conteo_nivel[nivel_actual + 1] += 1
			else:
				duplicados_descartados += 1

			if (nivel_actual + 1) < profundidad_maxima and username not in visitados and username not in en_cola:
				cola.append((username, nivel_actual + 1))
				en_cola.add(username)

	return catalog, aristas, eventos, conteo_nivel, duplicados_descartados, sin_username_descartados


def write_csv(path, rows, fieldnames):
	with open(path, 'w', newline='', encoding='utf-8') as csvfile:
		writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(rows)


def guardar_salidas(output_folder, canal, catalog, aristas, eventos):
	canales_rows = [
		{
			'username': info.get('username'),
			'title': info.get('title'),
			'verified': info.get('verified'),
			'participants_count': info.get('participants_count'),
			'date_created': info.get('date_created'),
			'language': info.get('language', 'unknown'),
			'nivel': info.get('nivel'),
		}
		for info in catalog.values()
	]
	write_csv(os.path.join(output_folder, 'similar_channels.csv'), canales_rows, [
		'username', 'title', 'verified', 'participants_count', 'date_created', 'language', 'nivel'
	])
	write_csv(os.path.join(output_folder, 'channel_recommendations_edges.csv'), [
		{'source': source, 'target': target} for source, target in sorted(aristas)
	], ['source', 'target'])
	write_csv(os.path.join(output_folder, 'channel_recommendations_events.csv'), eventos, [
		'step', 'nivel', 'source', 'target', 'discovered_at'
	])

	df = pd.DataFrame([chat_row(info) for info in catalog.values()])
	if len(df) > 0:
		df = df[chats_dataset_columns()]
		df.to_csv(os.path.join(output_folder, 'collected_chats.csv'), index=False, encoding='utf-8')
		df['username'].dropna().to_csv(os.path.join(output_folder, 'related_channels.csv'), index=False, header=False, encoding='utf-8')
		store_channels_related(
			os.path.join(output_folder, 'context', 'related_channel_log.csv'),
			df['username'].dropna(),
			output_folder,
		)

	grafo = nx.Graph()
	grafo.add_node(canal, title=canal, participants_count=-1, language='unknown', nivel=0, seed=True)
	for username, info in catalog.items():
		grafo.add_node(
			str(username),
			title=str(info.get('title') or ''),
			participants_count=-1 if info.get('participants_count') is None else int(info.get('participants_count')),
			language=str(info.get('language') or 'unknown'),
			nivel=-1 if info.get('nivel') is None else int(info.get('nivel')),
			seed=False,
		)
	for source, target in aristas:
		grafo.add_edge(source, target)
	nx.write_gexf(grafo, os.path.join(output_folder, 'channel_recommendations.gexf'))
	nx.write_graphml(grafo, os.path.join(output_folder, 'channel_recommendations.graphml'))


def parse_args():
	parser = argparse.ArgumentParser(description='Descubre canales similares usando la estructura del paquete.')
	parser.add_argument('--telegram-channel', '--canal', dest='canal', required=True, help='Canal semilla sin @.')
	parser.add_argument('--dataset-name', help='Nombre del dataset de salida. Default: <canal>_similar')
	parser.add_argument('--profundidad', type=int, default=1, help='Profundidad snowball.')
	parser.add_argument('--max-recomendaciones', type=int, default=None, help='Maximo de recomendaciones por canal.')
	parser.add_argument('--output', default='./dataset', help='Carpeta dataset (default: ./dataset).')
	return parser.parse_args()


async def main_async():
	args = parse_args()
	canal = args.canal.strip().lstrip('@')
	dataset_name = args.dataset_name or f'{canal}_similar'
	output_folder = os.path.join(args.output, dataset_name)
	create_dirs(output_folder)

	config = get_config_attrs()
	async with TelegramClient('session_file', int(config['api_id']), config['api_hash']) as cliente:
		catalog, aristas, eventos, conteo_nivel, duplicados, sin_username = await crear_grafo(
			cliente,
			canal=canal,
			profundidad_maxima=args.profundidad,
			max_recomendaciones=args.max_recomendaciones,
		)

	guardar_salidas(output_folder, canal, catalog, aristas, eventos)
	with open(os.path.join(output_folder, 'context', f'{dataset_name}_log.csv'), 'a', encoding='utf-8') as log:
		if log.tell() == 0:
			log.write('channel,type,date\n')
		log.write(f'{canal},similar_channels,{datetime.now()}\n')

	print('===== RESUMEN =====')
	print(f'Dataset: {output_folder}')
	print(f'Canal semilla: {canal}')
	print(f'Canales descubiertos: {len(catalog)}')
	print(f'Aristas: {len(aristas)}')
	print(f'Duplicados descartados: {duplicados}')
	print(f'Sugerencias sin username descartadas: {sin_username}')
	for nivel in range(1, args.profundidad + 1):
		print(f'Nivel {nivel}: {conteo_nivel.get(nivel, 0)}')


if __name__ == '__main__':
	asyncio.run(main_async())
