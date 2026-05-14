"""buddyMe 启动入口。python -m buddyMe 或 python main.py"""

import os
import sys
import time
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def main():
    from buddyMe.agent_moudle.agent import AgentMain
    from buddyMe.tool_moudle.baidu_search_tool import BaiduSearchTool

    model_name = os.environ.get("BUDDYME_MODEL", "glm_code_plan")

    print("=" * 60)
    print("buddyMe — 多模型智能体 + Skill")
    print(f"默认模型: {model_name}")
    print("输入 /help 查看可用命令")
    print("=" * 60)

    agent = AgentMain(model_name=model_name, data_dir=str(_SRC_DIR))
    agent.register_tool(BaiduSearchTool())

    while True:
        time.sleep(2)
        try:
            inp = input("query: ")
            reply = agent.invoke(inp)
            if reply:
                print(reply)
            if agent._last_cmd_should_exit:
                break
        except (KeyboardInterrupt, EOFError):
            print("\n再见!")
            agent.close()
            break


if __name__ == '__main__':
    main()

#查询北京5月17日天气，做一份博物馆导览，生成html格式给我