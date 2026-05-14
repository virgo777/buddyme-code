"""buddyMe CLI 入口"""

import os
import threading
import time

from rich.console import Console

from buddyMe.agent_moudle import agent
from buddyMe.tool_moudle.baidu_search_tool import BaiduSearchTool

console = Console()

_SPINNERS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _invoke_with_spinner(ag: agent.AgentMain, user_input: str) -> str:
    """在后台线程运行 invoke()，主线程显示 Rich 状态 spinner。"""
    result_box: list = [None]
    error_box: list = [None]

    def _worker():
        try:
            result_box[0] = ag.invoke(user_input)
        except Exception as exc:
            error_box[0] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    idx = 0
    with console.status("") as status:
        while t.is_alive():
            s = _SPINNERS[idx % len(_SPINNERS)]
            status.update(
                f"[bold cyan]{s} 思考中... "
                f"[dim](in: {ag._token_in} · out: {ag._token_out})[/]"
            )
            idx += 1
            t.join(timeout=0.25)

    if error_box[0] is not None:
        raise error_box[0]
    return result_box[0]


def main():
    # 捕获用户运行 buddyme 命令时所在的工作目录作为项目空间
    workspace_dir = os.getcwd()

    console.print("=" * 60, style="bold green")
    console.print("buddyMe — 多模型智能体 + Skill", style="bold green")
    console.print(f"项目空间: {workspace_dir}", style="cyan")
    console.print("输入 /help 查看可用命令", style="dim")
    console.print("=" * 60, style="bold green")

    model_name = "deepseek"
    ag = agent.AgentMain(model_name=model_name, workspace_dir=workspace_dir)
    ag.register_tool(BaiduSearchTool())

    while True:
        try:
            inp = input("query: ")
            reply = _invoke_with_spinner(ag, inp)
            if reply:
                console.print(reply)
        except (KeyboardInterrupt, EOFError):
            console.print("\n再见!", style="bold yellow")
            ag.close()
            break


if __name__ == "__main__":
    main()
