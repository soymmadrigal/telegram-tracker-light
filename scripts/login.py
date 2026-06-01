# -*- coding: utf-8 -*-

import asyncio

from api import get_connection
from utils import get_config_attrs


async def main():
	config = get_config_attrs()
	client = await get_connection(
		"session_file",
		int(config["api_id"]),
		config["api_hash"],
		config["phone"],
	)
	await client.disconnect()
	print("> Login check finished.", flush=True)


if __name__ == "__main__":
	asyncio.run(main())
