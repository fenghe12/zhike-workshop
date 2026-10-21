"""Convert execution failures into actionable messages without command details."""
import subprocess
import re


def task_error_message(error):
    if isinstance(error, subprocess.CalledProcessError):
        if error.returncode == 255:
            return '无法连接计算服务，请检查华为实例状态后重试。已完成结果已保留。'
        return '处理程序执行失败，请查看任务日志后重试。已完成结果已保留。'
    if isinstance(error, subprocess.TimeoutExpired):
        return '等待处理结果超时，请先确认原任务状态，再继续处理。'
    if isinstance(error, ImportError):
        return '运行环境缺少必要组件，请管理员检查依赖后重试。已完成结果已保留。'
    message = str(error)
    if re.search(r'/Users/|/home/|Traceback|\[.ssh.', message) or not re.search(r'[\u4e00-\u9fff]', message):
        return '课程处理未完成，请查看任务日志或联系管理员。已完成结果已保留。'
    return message[:500]
