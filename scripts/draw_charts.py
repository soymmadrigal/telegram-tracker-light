'''
This script is based on one made by Marcelino Madrigal
'''
import re
import os
import sys
import nltk
import pandas as pd
import dask.dataframe as dd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import seaborn as sns
import argparse
from adjustText import adjust_text
import matplotlib.ticker as ticker
from si_prefix import si_format
from wordcloud import WordCloud
from collections import Counter
from datetime import datetime
from nltk.corpus import stopwords
from utils import (
	chats_dataset_dtypes,msgs_dataset_dtypes
)
# Get start time
'''

graphics style

'''
# Graphics style
CHART_FIGSIZE = (19.2, 10.8)
CHART_DPI = 100
VIVID = ["#00B4D8", "#FF006E", "#8338EC", "#FB5607", "#3A86FF", "#06D6A0", "#FFBE0B", "#EF476F", "#118AB2", "#7209B7"]

available_fonts = {font.name for font in font_manager.fontManager.ttflist}
CHART_FONT = "Century Gothic" if "Century Gothic" in available_fonts else "DejaVu Sans"
sns.set_theme(style="whitegrid", palette=VIVID)
plt.rcParams.update({
	'font.size': 12,
	'font.family': CHART_FONT,
	'figure.figsize': CHART_FIGSIZE,
	'figure.dpi': CHART_DPI,
	'savefig.dpi': CHART_DPI,
	'axes.titlesize': 20,
	'axes.labelsize': 14,
})
RED = '#FF006E'
BLUE = '#00B4D8'
COLOR_TEXT = "#1f2937"
COLOR_GRID = "#d8dee8"

def save_chart(output_path):
	plt.tight_layout()
	plt.savefig(output_path, dpi=CHART_DPI)
	plt.close()

def fmt_thousands(value):
	return f"{int(value):,}".replace(",", ".")

def annotate_vertical_bars(ax, values):
	max_value = max(values) if len(values) else 0
	offset = max(max_value * 0.015, 1)
	for patch, value in zip(ax.patches, values):
		ax.text(
			patch.get_x() + patch.get_width() / 2,
			patch.get_height() + offset,
			fmt_thousands(value),
			ha="center",
			va="bottom",
			fontsize=12,
			fontweight="bold",
			color=COLOR_TEXT,
		)

# Formatting function for numbers
def si_formatter(x, pos):
		return si_format(x, precision=0)
'''

messages vs. attribute

'''
def create_timeline_lineplot(ddf, attribute_a, attribute_b, filter_b, title, title_a, title_b, output_path):
	start_time_chart = datetime.now()
	print(f"----> Graphic of {title_a} vs. {title_b}...")

	# Filter rows before adding attributes
	if filter_b:
		df_a = ddf[['date',attribute_a,attribute_b]]
		# filter attribute_a
		df_a = df_a[df_a[attribute_a] == 0]
		# Group by date and sum the attribute_b (with filter)
		df_b = df_a[['date', attribute_b]].dropna().compute()
	else:
		df_a = ddf[['date',attribute_a]]
		# filter attribute_a
		df_a = df_a[df_a[attribute_a] == 0]
		# Group by date and sum the attribute_b (without filter)
		df_b = ddf[['date', attribute_b]].dropna().compute()

	df_b['date'] = df_b['date'].dt.date	# Convert to date without time
	df_b = df_b.groupby('date').sum().reset_index()
	# Group by date and sum the attribute_a
	df_a = df_a[['date', attribute_a]].dropna().compute()
	df_a['date'] = df_a['date'].dt.date	# Convert to date without time
	df_a = df_a.groupby('date').count().reset_index()
	# Calculate statistics
	max_value = int(df_b[attribute_b].max())
	min_value = int(df_b[attribute_b].min())
	mean_value = int(df_b[attribute_b].mean())
	if max_value == 0:
		print(f'There are no {attribute_b}')
		return
	print(df_a.nlargest(10, 'is_forward'))
	# create line chart
	plt.figure(figsize=CHART_FIGSIZE, dpi=CHART_DPI)
	ax1 = sns.lineplot(data=df_a, x='date', y=attribute_a, color=BLUE, linewidth=1.5)
	ax2 = plt.twinx()
	ax2 = sns.scatterplot(data=df_b, x='date', y=attribute_b, color=RED, s=10)
	ax1.grid (color=COLOR_GRID)
	ax1.yaxis.set_major_formatter(ticker.FuncFormatter(si_formatter))
	ax2.yaxis.set_major_formatter(ticker.FuncFormatter(si_formatter))
	# Add labels to the maximum 5 values
	top_2 = df_b.nlargest(2, attribute_b)
# Annotate top values
	offset = 0
	for i, row in top_2.iterrows():
		plt.text(row['date'], row[attribute_b] + offset,
			f"{row['date'].strftime('%d-%m-%Y')}\n{int(row[attribute_b]):,}".replace(',', '.'),
			fontsize=10, ha='right', color=COLOR_TEXT)
		offset -= row[attribute_b] * 0.1	# Move each label down 10% to avoid overlapping
# complete details with matplotlib
	plt.title(title, fontsize=16)
	ax1.set_ylabel (title_a, fontsize=14, color=BLUE)
	ax1.set_xlabel ("")
	ax1.yaxis.set_tick_params(labelsize=12,labelcolor=BLUE)

	ax2.set_ylabel (title_b , fontsize=14, color=RED)
	ax2.set_xlabel ("")
	ax2.yaxis.set_tick_params(labelsize=12,labelcolor=RED)
 
	# Add box with statistics
	stats_text = f"{attribute_b}\nMax: {max_value:,}\nMin: {min_value:,}\nMedia: {mean_value:,}".replace(',', '.')
	plt.gcf().text(0.1, 0.75, stats_text, fontsize=12,color = COLOR_TEXT,
		bbox=dict(facecolor='white', alpha=0.6))
	save_chart(output_path)
	print(f'Successfully saved in {output_path}.')
	print(f'Last {datetime.now()- start_time_chart} ')

'''

Bar chart of top 15 domains by totals

'''
def create_top_domains_barplot(ddf, title, output_path):
	start_time_chart = datetime.now()
	print("----> Bar chart of top 15 domains by totals...")

	# Count the occurrences of each domain
	domain_counts = ddf['domain'].value_counts().compute().reset_index()
	domain_counts.columns = ['domain', 'count']

	# Select top 15
	top_15_domains = domain_counts.nlargest(15, 'count')

	# Create bar chart
	plt.figure(figsize=CHART_FIGSIZE, dpi=CHART_DPI)
	sns.barplot(data=top_15_domains, x='count', y='domain', palette=VIVID, hue='domain', legend=False)

	plt.title(title, fontsize=16)
	plt.xlabel('Total', fontsize=14)
	plt.ylabel('Dominio', fontsize=14)
	plt.xticks(rotation=0)

	save_chart(output_path)
	print(f'Successfully saved in {output_path}.')
	print(f'Last {datetime.now()- start_time_chart} ')

'''

create line chart with cumulative total of top 10 most mentioned domains by date

'''
def create_top_domains_timeline(ddf, title, output_path):
	start_time_chart = datetime.now()
	print("----> Create line chart with cumulative total of top 10 most mentioned domains by date...")
	# Count the occurrences of each domain
	domain_counts = ddf['domain'].value_counts().compute().reset_index()
	domain_counts.columns = ['domain', 'count']
	# Select top 15
	top_10_domains = domain_counts.nlargest(10, 'count')['domain']

	# Filter the DataFrame to include only the top 10 domains
	ddf_top_10 = ddf[ddf['domain'].isin(top_10_domains)].compute()

	# Create a column for the date without the time
	ddf_top_10['date'] = ddf_top_10['date'].dt.date
	# Group by date and domain and count occurrences
	df_grouped = ddf_top_10.groupby(['date', 'domain']).size().reset_index(name='count')

	# Create cumulative count column
	df_grouped['cumulative_count'] = df_grouped.groupby('domain')['count'].cumsum()
	df_grouped= df_grouped.sort_values(by=['cumulative_count','domain'], ascending=[False, False])
	color_lines = sns.color_palette(VIVID)
	# Create the line chart
	plt.figure(figsize=CHART_FIGSIZE, dpi=CHART_DPI)
	sns.lineplot(data=df_grouped, x='date', y='cumulative_count', hue='domain', palette=VIVID, linewidth=2.0)
# Annotate top values
	i_color = 0
	texts = []
	for domain in top_10_domains:
		rows = df_grouped.loc[df_grouped['domain'] == domain, :].head(1)
		for i, row in rows.iterrows():
			text = plt.text(row['date'], row['cumulative_count'],
				f"{row['domain']}({int(row['cumulative_count']):,})".replace(',', '.'),
				color = color_lines[i_color])
			i_color += 1
			texts.append(text)
	adjust_text(texts, arrowprops=dict(arrowstyle='-', color='grey'))
	plt.title(title, fontsize=16)

	plt.xlabel('', fontsize=14)
	plt.ylabel('Cumulative total of mentions', fontsize=14)
	plt.xticks(rotation=0)
	plt.legend('',frameon=False)

	save_chart(output_path)
	print('Successfully saved in {output_path}.')
	print(f'Last {datetime.now()- start_time_chart} ')

'''
Clean text

'''
# remove URLs and convert to lowercase
def clean_text(text):
		text = re.sub(r'http\S+', '', text)	# Eliminar URLs
		text = text.lower()	# Pasar a minúsculas
		return text
'''

Create a word cloud

'''


# Create a word cloud of the messages using a random sample of 10%
def create_wordcloud(ddf, column, output_path):
	start_time_chart = datetime.now()
	print(f"---->Generating word cloud of {column}...")
	#Get a random sample of 10% of the messages
	sample_ddf = ddf[column].dropna().sample(frac=0.1, random_state=1).compute().astype(str)
	counts_all = Counter()
	stop_words = set(stopwords.words('spanish') + stopwords.words('english'))
	for line in sample_ddf:
		counts_line = WordCloud(stopwords=stop_words).process_text(line)
		counts_all.update(counts_line)
		# Generate word cloud
	font_path = None
	if CHART_FONT == "Century Gothic":
		for font in font_manager.fontManager.ttflist:
			if font.name == "Century Gothic":
				font_path = font.fname
				break
	wordcloud = WordCloud(
		width=1920,
		height=1080,
		background_color='white',
		stopwords=stop_words,
		colormap='turbo',
		font_path=font_path,
	).generate_from_frequencies(counts_all)

	# Get the 5 most used words
	top_5_words = list(wordcloud.words_.keys())[:5]

	# Mostrar y guardar nube de palabras
	plt.figure(figsize=CHART_FIGSIZE, dpi=CHART_DPI)
	plt.imshow(wordcloud, interpolation='bilinear')
	plt.axis('off')
	save_chart(output_path)
	print(f'Successfully saved in {output_path}.')
	print(f'Last {datetime.now()- start_time_chart}')

	return top_5_words

def create_kpi_cards(ddf, title, output_path):
	start_time_chart = datetime.now()
	print("----> KPI cards...")
	df = ddf[['channel_name', 'views', 'number_forwards']].compute()
	df['views'] = pd.to_numeric(df['views'], errors='coerce').fillna(0)
	df['number_forwards'] = pd.to_numeric(df['number_forwards'], errors='coerce').fillna(0)
	kpis = [
		("Mensajes", len(df), VIVID[0]),
		("Canales", df['channel_name'].fillna("(sin_canal)").nunique(), VIVID[2]),
		("Vistas", df['views'].sum(), VIVID[5]),
		("Forwards", df['number_forwards'].sum(), VIVID[1]),
	]
	fig, ax = plt.subplots(figsize=CHART_FIGSIZE, dpi=CHART_DPI)
	fig.patch.set_facecolor("#f7f9fc")
	ax.set_facecolor("#f7f9fc")
	ax.axis("off")
	ax.text(0.05, 0.88, title, transform=ax.transAxes, fontsize=30, fontweight="bold", color="#111827")
	ax.text(0.05, 0.82, "Resumen ejecutivo del dataset", transform=ax.transAxes, fontsize=15, color="#4b5563")
	card_w = 0.205
	card_h = 0.42
	xs = [0.05, 0.285, 0.52, 0.755]
	for x, (label, value, color) in zip(xs, kpis):
		card = plt.Rectangle((x, 0.28), card_w, card_h, transform=ax.transAxes, facecolor="white", edgecolor="#e5e7eb", linewidth=1.2)
		ax.add_patch(card)
		ax.add_patch(plt.Rectangle((x, 0.28 + card_h - 0.035), card_w, 0.035, transform=ax.transAxes, facecolor=color, edgecolor=color))
		ax.text(x + 0.025, 0.58, label.upper(), transform=ax.transAxes, fontsize=13, fontweight="bold", color="#4b5563")
		ax.text(x + 0.025, 0.43, fmt_thousands(value), transform=ax.transAxes, fontsize=34, fontweight="bold", color=color)
	save_chart(output_path)
	print(f'Successfully saved in {output_path}.')
	print(f'Last {datetime.now()- start_time_chart}')

def create_top_forward_received(ddf, title, output_path):
	start_time_chart = datetime.now()
	print("----> Top 10 channels by forwards received...")
	df = ddf[['channel_name', 'number_forwards']].compute()
	df['channel_name'] = df['channel_name'].fillna("(sin_canal)").astype(str)
	df['number_forwards'] = pd.to_numeric(df['number_forwards'], errors='coerce').fillna(0)
	top = df.groupby('channel_name', as_index=False)['number_forwards'].sum().nlargest(10, 'number_forwards')
	if len(top) == 0 or top['number_forwards'].sum() == 0:
		print('There are no received forwards to plot.')
		return
	plt.figure(figsize=CHART_FIGSIZE, dpi=CHART_DPI)
	ax = sns.barplot(data=top, x='channel_name', y='number_forwards', palette=VIVID, hue='channel_name', legend=False)
	annotate_vertical_bars(ax, top['number_forwards'].tolist())
	ax.set_title(title, fontsize=22, fontweight="bold")
	ax.set_xlabel("")
	ax.set_ylabel("Forwards recibidos")
	ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: fmt_thousands(x)))
	plt.xticks(rotation=35, ha='right')
	ax.margins(y=0.15)
	save_chart(output_path)
	print(f'Successfully saved in {output_path}.')
	print(f'Last {datetime.now()- start_time_chart}')

def create_top_forward_makers(ddf, title, output_path):
	start_time_chart = datetime.now()
	print("----> Top 10 channels by forwards made...")
	df = ddf[['channel_name', 'is_forward']].compute()
	df['channel_name'] = df['channel_name'].fillna("(sin_canal)").astype(str)
	df['is_forward'] = pd.to_numeric(df['is_forward'], errors='coerce').fillna(0)
	top = df.groupby('channel_name', as_index=False)['is_forward'].sum().nlargest(10, 'is_forward')
	if len(top) == 0 or top['is_forward'].sum() == 0:
		print('There are no sent forwards to plot.')
		return
	plt.figure(figsize=CHART_FIGSIZE, dpi=CHART_DPI)
	ax = sns.barplot(data=top, x='channel_name', y='is_forward', palette=VIVID, hue='channel_name', legend=False)
	annotate_vertical_bars(ax, top['is_forward'].tolist())
	ax.set_title(title, fontsize=22, fontweight="bold")
	ax.set_xlabel("")
	ax.set_ylabel("Forwards realizados")
	ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: fmt_thousands(x)))
	plt.xticks(rotation=35, ha='right')
	ax.margins(y=0.15)
	save_chart(output_path)
	print(f'Successfully saved in {output_path}.')
	print(f'Last {datetime.now()- start_time_chart}')

'''

Start script


'''

start_time = datetime.now()
print(f"Script start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

# Download NLTK stopwords
nltk.download('stopwords')

'''

Arguments

'''

parser = argparse.ArgumentParser(description='Arguments.')
parser.add_argument(
	'--dataset',
	type=str,
	required=False,
	help='Specifies a dataset.'
)
parser.add_argument(
	'--channel',
	type=str,
	required=False,
	help='Specifies a dataset.'
)
# parse arguments
args = vars(parser.parse_args())
if args['dataset']:
	dataset = args['dataset']
	base_path = f'./dataset/{dataset}/'
	if not os.path.exists(base_path):
		print(f'{dataset} does not exist')
		sys.exit()
if args['channel']:
	channel = args['channel']
	base_path = f'./data/{channel}/'
	dataset = channel
	if not os.path.exists(base_path):
		print(f'{channel} does not exist')
		sys.exit()
base_images_path = f'{base_path}/images'
if not os.path.exists(base_images_path):
	os.makedirs(f'{base_images_path}', exist_ok=True)
csv_file_path = f'{base_path}/msgs_dataset.csv'


# Change matplotlib backend to 'Agg'
plt.close('all')


'''

read and clean data

'''
# Read CSV file using dask with specified data types
print("----> Reading CSV file...")
ddf = dd.read_csv(csv_file_path, dtype=msgs_dataset_dtypes(), on_bad_lines='skip', engine='python')
print(f'Last {datetime.now()- start_time} ')
# Convert 'date' column to datetime
ddf['date'] = dd.to_datetime(ddf['date'], errors='coerce')
# Filter rows with valid dates
ddf = ddf.dropna(subset=['date'])


'''

Creating KPI and forwards ranking charts

'''
create_kpi_cards(ddf,
	f'{dataset}: KPIs principales',
	f'{base_images_path}/00_kpi_cards.png')

create_top_forward_received(ddf,
	f'{dataset}: Top 10 canales que mas forwards reciben',
	f'{base_images_path}/06_top10_forwards_recibidos.png')

create_top_forward_makers(ddf,
	f'{dataset}: Top 10 canales que mas forwards hacen',
	f'{base_images_path}/07_top10_forwards_realizados.png')


'''

Creating line graphs of time distributions

'''
create_timeline_lineplot(ddf, 'is_forward','views', True,
	f'{dataset}: Temporal distribution of messages vs. views',
	'Num. of original msgs per day',
	'Views per day',
	f'{base_images_path}/timeline_views.png')
create_timeline_lineplot(ddf, 'is_forward','is_forward', False,
	f'{dataset}: Temporal distribution of messages vs. forwards send',
	'Num. of original msgs per day',
	'Forwards per day',
	f'{base_images_path}/timeline_forwards_send.png')
create_timeline_lineplot(ddf, 'is_forward','number_forwards', True,
	f'{dataset}: Temporal distribution of messages vs. forwards received',
	'Num. of original msgs per day',
	'Forwards per day',
	f'{base_images_path}/timeline_forwards_received.png')
create_timeline_lineplot(ddf, 'is_forward', 'is_reply', False,
	f'{dataset}: Temporal distribution of messages vs. replies send',
	'Num. of original msgs per day',
	'Replies per day',
	f'{base_images_path}/timeline_replies_send.png')
create_timeline_lineplot(ddf, 'is_forward', 'number_replies', True,
	f'{dataset}: Temporal distribution of messages vs. replies received',
	'Num. of original msgs per day',
	'Replies per day',
	f'{base_images_path}/timeline_replies_received.png')
'''

Creating domain graphs

'''
create_top_domains_barplot(ddf,
	f'{dataset}: Top 15 Dominios por Totales',
	f'{base_images_path}//top_15_domains.png'),

create_top_domains_timeline(ddf,
	f'{dataset}: Cumulative temporal distribution of the 10 most mentioned domains',
	f'{base_images_path}/top_10_domains_timeline.png')

'''

Creating word cloud

'''
# Apply cleanup function to message column
ddf['cleaned_message'] = ddf['message'].dropna().apply(clean_text, meta=('message', 'object'))
# Create the word cloud for clean messages and get the 5 most used words
top_5_words = create_wordcloud(ddf, 'cleaned_message', f'{base_images_path}/wordcloud_messages.png')

'''

End script

'''
plt.close('all')
# Put end time
end_time = datetime.now()
print(f"Hora final del script: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

