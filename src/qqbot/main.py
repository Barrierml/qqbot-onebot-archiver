from __future__ import annotations

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from .config import load_config


def main() -> None:
    config = load_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)

    nonebot.init(
        driver="~fastapi+~websockets",
        host=config.host,
        port=config.port,
        onebot_ws_urls=config.onebot_ws_urls,
        onebot_access_token=config.onebot_access_token,
        nickname=set(config.nicknames),
        superusers=set(config.superusers),
        command_start={"/"},
        log_level=config.log_level,
    )

    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)
    nonebot.load_plugin("qqbot.plugins.archive")
    nonebot.run()


if __name__ == "__main__":
    main()

