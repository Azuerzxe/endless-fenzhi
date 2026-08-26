import json
import sys
import time
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


# ---------- 极简日志工具（输出到 stderr，MaaFramework 会捕获并显示） ----------
def _log(level_short: str, msg: str):
    """输出格式：level_short:message"""
    print(f"{level_short}:{msg}", file=sys.stderr, flush=True)


def log_info(msg):
    _log("info", msg)


def log_debug(msg):
    _log("debug", msg)


def log_warn(msg):
    _log("warn", msg)


def log_error(msg):
    _log("err", msg)


@AgentServer.custom_action("returnOCR")
class ReturnOCR(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        log_info("========== returnOCR 开始执行 ==========")

        if not argv.custom_action_param:
            log_warn("custom_action_param 为空，跳过")
            return CustomAction.RunResult(success=True)

        try:
            param = json.loads(argv.custom_action_param)
            log_debug(f"解析参数: {param}")
        except json.JSONDecodeError as e:
            log_error(f"JSON 解析失败: {e}")
            return CustomAction.RunResult(success=False)

        recognition_name = param.get("recognition_name", "")
        return_text = param.get("return_text", "")
        roi = param.get("roi", [])
        hold_position = param.get("hold_position", [])
        hold_before = param.get("hold_before", 0.0)
        click_before = param.get("click_before", [])
        wait_before = param.get("wait_before", 500)
        click_target = param.get("click_target", [])
        hold_after = param.get("hold_after", 0.0)

        if not recognition_name:
            log_warn("缺少 recognition_name")
            return CustomAction.RunResult(success=False)

        # ---------- 辅助函数 ----------
        def do_tap(roi, hold_seconds=0.0):
            if not roi or len(roi) != 4:
                return
            x = roi[0] + roi[2] // 2
            y = roi[1] + roi[3] // 2
            if hold_seconds > 0:
                log_debug(f"长按坐标: ({x}, {y})，持续 {hold_seconds} 秒")
                context.tasker.controller.post_swipe(x, y, x, y, duration=int(hold_seconds * 1000)).wait()
            else:
                log_debug(f"点击坐标: ({x}, {y})")
                context.tasker.controller.post_click(x, y).wait()

        # ---------- 识别前操作 ----------
        reco_result = None
        if hold_position and len(hold_position) == 4 and hold_before > 0:
            x = hold_position[0] + hold_position[2] // 2
            y = hold_position[1] + hold_position[3] // 2
            log_info(f"【按住模式】按住坐标: ({x}, {y})，等待 {hold_before} 秒后截图")
            context.tasker.controller.post_touch_down(x, y).wait()
            time.sleep(hold_before)
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
                log_debug(f"使用动态 ROI: {roi}")
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)
            context.tasker.controller.post_touch_up().wait()
            log_debug("已松开手指")
            if wait_before > 0:
                time.sleep(wait_before / 1000.0)
        elif click_before:
            log_info("【点击模式】识别前点击")
            do_tap(click_before, 0)
            if wait_before > 0:
                time.sleep(wait_before / 1000.0)
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)
        else:
            log_info("【无前置操作】直接截图识别")
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)

        # ---------- 处理结果 ----------
        if not reco_result:
            log_warn("reco_result 为 None")
            return CustomAction.RunResult(success=True)
        log_debug(f"reco_result.hit = {reco_result.hit}")
        if not reco_result.hit:
            log_warn(f"OCR 识别失败: {recognition_name}")
            return CustomAction.RunResult(success=True)

        best = reco_result.best_result
        if not best:
            log_warn(f"best_result 为空: {recognition_name}")
            return CustomAction.RunResult(success=True)

        recognized_text = best.text if best.text is not None else ""
        full_message = f"{return_text}{recognized_text}"
        # 关键输出：显示在 UI
        log_info(f"{full_message}")

        if not recognized_text:
            log_warn("识别到的文本为空字符串")

        # ---------- 后置操作 ----------
        if click_target:
            log_info("执行后置点击")
            do_tap(click_target, hold_after)

        log_info("========== returnOCR 执行完毕 ==========")
        return CustomAction.RunResult(success=True)