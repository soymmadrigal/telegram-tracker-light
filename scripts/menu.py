# -*- coding: utf-8 -*-

# import modules
import os
import sys
from pathlib import Path

if os.name == 'nt':
	copy = 'copy'
else:
	copy = 'cp'
exit = 'n'
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / 'scripts'
os.chdir(ROOT)
data_path = './data'
dataset_path = './dataset'
python_cmd = f'"{sys.executable}"'

def script_cmd(name):
	return f'{python_cmd} "{SCRIPTS_DIR / name}"'

try:
	while exit != 'y':
		print ('--------------------------------')
		print ('What function do you want to run?')
		print ('--------------------------------')
		print ('1. Initial setup / Telegram API credentials')
		print ('   You need api_id and api_hash from https://my.telegram.org/auth?to=apps')
		print ('2. Get a channel')
		print ('3. Get a snowball from a channel')
		print ('4. Get a channel list')
		print ('5. Get charts')
		print ('6. get graph (gexf format)')
		print ('7. get summary (xlsx format)')
		print ('8. update channels')
		print ('9. Search messages in channels')
		print ('10. Discover similar channels')
		print ('11. Find payment IOCs')
		print ('12. Exit')
		print (' ')
		while True:
			try:
				option = int(input('--> Enter option: '))
				if option in range (1,13):
					break
				else:
					print('type a number from 1 to 12')
			except:
				print('type a number from 1 to 12')
			'''
			Initial setup
			'''
		if option == 1:
			print('--------> initial setup')
			print('You will need api_id and api_hash from:')
			print('https://my.telegram.org/auth?to=apps')
			os.system(script_cmd('setup.py'))
			'''
			Get a channel
			'''
		if option == 2:
			channel = input ('Enter channel name: ')
			channel_path = f'{data_path}/{channel}'
			print(f'Output on {channel_path}')
			print(f'Download channel {channel}')
			os.system(script_cmd('main.py') +
				f' --telegram-channel {channel}')
		'''
		Get a snowball from a user
		'''
		if option == 3:
			channel_root = input ('root channel (must have been downloaded before): ')
			channel_list = f'{data_path}/{channel_root}/related_channels.csv'
			if not os.path.exists(channel_list):
				print(f'{channel_root} must have been downloaded before')
			else:
				os.system('' +
					script_cmd('build-dataset.py') +
					f' --dataset-name {channel_root}_n2' +
					f' --channel-list {channel_list}') 
			'''
			Get a list channels
			'''
		if option == 4:
			dataset_name = input ('Enter dataset name: ')
			if not os.path.exists(f'{dataset_path}/{dataset_name}/channel_list.csv'):
				channel_list = input ('Enter file with the list of channels: ')
			else:
				channel_list = f'{dataset_path}/{dataset_name}/channel_list.csv'
			os.system('' +
				script_cmd('build-dataset.py') +
				f' --dataset-name {dataset_name}' +
				f' --channel-list {channel_list}')
			'''
			Get charts
			'''
		if option == 5:
			dataset_name = input ('Enter dataset or channel name: ')
			if os.path.exists(f'./data/{dataset_name}'):
				print(f'--------> draw charts from channel {dataset_name}')
				os.system (script_cmd('draw_charts.py') + f' --channel {dataset_name}')
			elif os.path.exists(f'./dataset/{dataset_name}/'):
				print(f'--------> draw charts from dataset {dataset_name}')
				os.system (script_cmd('draw_charts.py') + f' --dataset {dataset_name}')
			else:
				print(f'{dataset_name} does not exist')
			'''
			Get graph
			'''
		if option == 6:
			dataset_name = input ('Enter dataset or channel name: ')
			if os.path.exists(f'./dataset/{dataset_name}/'):
				print(f'--------> Get graph from dataset {dataset_name}')
				os.system (script_cmd('net.py') + f' --dataset {dataset_name}')
			else:
				print(f'{dataset_name} does not exist')
			'''
			Get summary channels
			'''
		if option == 7:
			flag_dataset = input ('Dataset summary? (y | n) : ')
			flag_channel = input ('Channels summary? (y | n) : ')
			if flag_channel.lower() == 'y':
				if os.path.exists('./data'):
					print('--------> Get channels summary')
					os.system (script_cmd('summary_channels.py'))
				else:
					print('data dir does not exist')
			if flag_dataset.lower() == 'y':
				if os.path.exists('./dataset'):
					print('--------> Get datasets summary')
					os.system (script_cmd('summary_datasets.py'))
				else:
					print('datasets dir does not exist')
			'''
			update channels
			'''
		if option == 8:
			print('--------> update channels')
			os.system (script_cmd('update_channels.py'))
			'''
			Search messages
			'''
		if option == 9:
			terms = input ('Terms to search (comma or OR separated): ')
			mode = input ('Search one channel or a channel list? (c | l): ')
			if mode.lower() == 'c':
				channel = input ('Enter channel name: ')
				os.system (script_cmd('search_messages.py') +
					f' --terms "{terms}"' +
					f' --telegram-channel {channel}')
			else:
				dataset_name = input ('Enter dataset name: ')
				channel_list = input ('Enter file with the list of channels: ')
				os.system (script_cmd('search_messages.py') +
					f' --terms "{terms}"' +
					f' --dataset-name {dataset_name}' +
					f' --channel-list {channel_list}')
			'''
			Discover similar channels
			'''
		if option == 10:
			channel = input ('Enter seed channel name: ')
			dataset_name = input ('Enter output dataset name [Enter = channel_similar]: ')
			profundidad = input ('Depth [1]: ') or '1'
			max_recomendaciones = input ('Max recommendations per channel [Enter = all]: ')
			cmd = script_cmd('similar_channels.py') + f' --telegram-channel {channel}' + f' --profundidad {profundidad}'
			if dataset_name.strip():
				cmd += f' --dataset-name {dataset_name}'
			if max_recomendaciones.strip():
				cmd += f' --max-recomendaciones {max_recomendaciones}'
			os.system(cmd)
			'''
			Find payment IOCs
			'''
		if option == 11:
			name = input ('Enter dataset or channel name: ')
			if os.path.exists(f'./data/{name}'):
				os.system (script_cmd('filtrobtc.py') + f' --channel {name}')
			elif os.path.exists(f'./dataset/{name}'):
				os.system (script_cmd('filtrobtc.py') + f' --dataset {name}')
			else:
				print(f'{name} does not exist')
			'''
			Exit
			'''
		elif option == 12:
			exit = 'y'
			break
except KeyboardInterrupt:
	print ('\nGoodbye!')
	sys.exit(0)
