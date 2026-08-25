import json
import sys
import time
import traceback

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


@AgentServer.custom_action("returnOCR")
class ReturnOCR(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 使用 context.logger 输出，保证在 UI 显示
        context.logger.info("========== returnOCR 开始执行 ==========")

        if not argv.custom_action_param:
            context.logger.warning("custom_action_param 为空，跳过")
            return CustomAction.RunResult(success=True)

        try:
            param = json.loads(argv.custom_action_param)
            context.logger.debug(f"解析参数: {param}")
        except json.JSONDecodeError as e:
            context.logger.error(f"JSON 解析失败: {e}")
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
            context.logger.warning("缺少 recognition_name")
            return CustomAction.RunResult(success=False)

        # ---------- 辅助函数 ----------
        def do_tap(roi, hold_seconds=0.0):
            if not roi or len(roi) != 4:
                return
            x = roi[0] + roi[2] // 2
            y = roi[1] + roi[3] // 2
            if hold_seconds > 0:
                context.logger.debug(f"长按坐标: ({x}, {y})，持续 {hold_seconds} 秒")
                context.tasker.controller.post_swipe(x, y, x, y, duration=int(hold_seconds * 1000)).wait()
            else:
                context.logger.debug(f"点击坐标: ({x}, {y})")
                context.tasker.controller.post_click(x, y).wait()

        # ---------- 识别前操作 ----------
        reco_result = None
        if hold_position and len(hold_position) == 4 and hold_before > 0:
            x = hold_position[0] + hold_position[2] // 2
            y = hold_position[1] + hold_position[3] // 2
            context.logger.info(f"【按住模式】按住坐标: ({x}, {y})，等待 {hold_before} 秒后截图")
            # 1. touch down
            context.tasker.controller.post_touch_down(x, y).wait()
            # 2. 等待文字出现
            time.sleep(hold_before)
            # 3. 截图
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
                context.logger.debug(f"使用动态 ROI: {roi}")
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)
            # 4. touch up
            context.tasker.controller.post_touch_up().wait()
            context.logger.debug("已松开手指")
            if wait_before > 0:
                time.sleep(wait_before / 1000.0)
        elif click_before:
            context.logger.info("【点击模式】识别前点击")
            do_tap(click_before, 0)
            if wait_before > 0:
                time.sleep(wait_before / 1000.0)
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)
        else:
            context.logger.info("【无前置操作】直接截图识别")
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)

        # ---------- 处理结果 ----------
        if not reco_result:
            context.logger.warning("reco_result 为 None")
            return CustomAction.RunResult(success=True)
        context.logger.debug(f"reco_result.hit = {reco_result.hit}")
        if not reco_result.hit:
            context.logger.warning(f"OCR 识别失败: {recognition_name}")
            return CustomAction.RunResult(success=True)

        best = reco_result.best_result
        if not best:
            context.logger.warning(f"best_result 为空: {recognition_name}")
            return CustomAction.RunResult(success=True)

        recognized_text = best.text if best.text is not None else ""
        full_message = f"{return_text}{recognized_text}"
        # 使用 context.logger.info 输出，保证在 UI 显示
        context.logger.info(f"✅ {full_message}")   # 这里会显示在 UI 日志中

        if not recognized_text:
            context.logger.warning("识别到的文本为空字符串")

        # ---------- 后置操作 ----------
        if click_target:
            context.logger.info("执行后置点击")
            do_tap(click_target, hold_after)

        context.logger.info("========== returnOCR 执行完毕 ==========")
        return CustomAction.RunResult(success=True)