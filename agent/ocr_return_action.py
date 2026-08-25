import json
import sys
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

try:
    from loguru import logger
except ImportError:
    import logging
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
    logger = logging


@AgentServer.custom_action("returnOCR")
class ReturnOCR(CustomAction):
    """
    自定义动作：
    支持按住（touch down）期间截图识别，然后松开；也支持普通点击后识别。

    custom_action_param 参数：
        recognition_name (必填): 识别节点的名称
        return_text (可选): 输出日志的前缀
        roi (可选): 动态覆盖识别区域 [x,y,w,h]

        # 识别前操作（二选一）：
        # 模式1：按住期间识别（常用）
        hold_position (可选): 按住位置 [x,y,w,h]
        hold_before (可选): 按住后等待多少秒再截图（默认1.0）
        # 模式2：普通点击后识别
        click_before (可选): 点击位置 [x,y,w,h]
        wait_before (可选): 点击/按住后额外等待毫秒数（默认500）

        # 识别后操作（可选）：
        click_target (可选): 点击位置 [x,y,w,h]
        hold_after (可选): 若 >0，则 click_target 执行长按秒数（默认0即普通点击）
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        if not argv.custom_action_param:
            return CustomAction.RunResult(success=True)
        try:
            param = json.loads(argv.custom_action_param)
        except json.JSONDecodeError:
            logger.error("returnOCR 参数不是合法 JSON")
            return CustomAction.RunResult(success=False)

        recognition_name = param.get("recognition_name", "")
        return_text = param.get("return_text", "")
        roi = param.get("roi", [])
        hold_position = param.get("hold_position", [])
        hold_before = param.get("hold_before", 1.0)  # 按住后等待秒数
        click_before = param.get("click_before", [])
        wait_before = param.get("wait_before", 500)
        click_target = param.get("click_target", [])
        hold_after = param.get("hold_after", 0.0)

        if not recognition_name:
            logger.warning("returnOCR 缺少 recognition_name")
            return CustomAction.RunResult(success=False)

        # ---------- 辅助函数：普通点击或长按 ----------
        def do_tap(roi, hold_seconds=0.0):
            if not roi or len(roi) != 4:
                return
            x = roi[0] + roi[2] // 2
            y = roi[1] + roi[3] // 2
            if hold_seconds > 0:
                logger.debug(f"长按坐标: ({x}, {y})，持续 {hold_seconds} 秒")
                context.tasker.controller.post_swipe(x, y, x, y, duration=int(hold_seconds * 1000)).wait()
            else:
                logger.debug(f"点击坐标: ({x}, {y})")
                context.tasker.controller.post_click(x, y).wait()

        # ---------- 识别前操作 ----------
        # 优先处理按住期间识别（hold_position + hold_before）
        if hold_position and len(hold_position) == 4 and hold_before > 0:
            x = hold_position[0] + hold_position[2] // 2
            y = hold_position[1] + hold_position[3] // 2
            logger.debug(f"按住坐标: ({x}, {y})，等待 {hold_before} 秒后截图识别")
            # 1. touch down（按住）
            context.tasker.controller.post_touch_down(x, y).wait()
            # 2. 等待文字出现
            time.sleep(hold_before)
            # 3. 截图并识别（此时手指仍按住）
            image = context.tasker.controller.post_screencap().wait().get()
            # 构造识别覆盖
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
                logger.debug(f"使用动态 ROI: {roi}")
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)
            # 4. touch up（松开）
            context.tasker.controller.post_touch_up().wait()
            # 5. 额外等待（可选）
            if wait_before > 0:
                time.sleep(wait_before / 1000.0)

        # 否则处理普通点击（click_before）
        elif click_before:
            do_tap(click_before, 0)  # 普通点击
            if wait_before > 0:
                time.sleep(wait_before / 1000.0)
            # 截图识别
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
                logger.debug(f"使用动态 ROI: {roi}")
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)

        else:
            # 如果没有前置操作，直接截图识别
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
                logger.debug(f"使用动态 ROI: {roi}")
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)

        # ---------- 处理识别结果 ----------
        if not (reco_result and reco_result.hit):
            logger.warning(f"OCR 识别失败: {recognition_name}")
            return CustomAction.RunResult(success=True)

        best = reco_result.best_result
        if not best:
            logger.warning(f"识别命中但 best_result 为空: {recognition_name}")
            return CustomAction.RunResult(success=True)

        recognized_text = best.text if best.text is not None else ""
        logger.info(f"{return_text}{recognized_text}")

        # ---------- 识别后操作 ----------
        if click_target:
            do_tap(click_target, hold_after)

        return CustomAction.RunResult(success=True)