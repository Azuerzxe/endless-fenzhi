import json
import sys
import time
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


@AgentServer.custom_action("returnOCR")
class ReturnOCR(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 不输出任何过程日志，只输出最终 OCR 结果

        if not argv.custom_action_param:
            return CustomAction.RunResult(success=True)

        try:
            param = json.loads(argv.custom_action_param)
        except json.JSONDecodeError:
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
            return CustomAction.RunResult(success=False)

        # ---------- 辅助函数 ----------
        def do_tap(roi, hold_seconds=0.0):
            if not roi or len(roi) != 4:
                return
            x = roi[0] + roi[2] // 2
            y = roi[1] + roi[3] // 2
            if hold_seconds > 0:
                context.tasker.controller.post_swipe(x, y, x, y, duration=int(hold_seconds * 1000)).wait()
            else:
                context.tasker.controller.post_click(x, y).wait()

        # ---------- 识别前操作 ----------
        reco_result = None
        if hold_position and len(hold_position) == 4 and hold_before > 0:
            x = hold_position[0] + hold_position[2] // 2
            y = hold_position[1] + hold_position[3] // 2
            context.tasker.controller.post_touch_down(x, y).wait()
            time.sleep(hold_before)
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)
            context.tasker.controller.post_touch_up().wait()
            if wait_before > 0:
                time.sleep(wait_before / 1000.0)
        elif click_before:
            do_tap(click_before, 0)
            if wait_before > 0:
                time.sleep(wait_before / 1000.0)
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)
        else:
            image = context.tasker.controller.post_screencap().wait().get()
            override = {}
            if roi and len(roi) == 4:
                override[recognition_name] = {"roi": roi}
            reco_result = context.run_recognition(recognition_name, image, pipeline_override=override)

        # ---------- 处理结果 ----------
        if not reco_result or not reco_result.hit:
            # 识别失败时保持安静，或可输出一条警告（按需取消注释）
            # print("warn:OCR识别失败", file=sys.stderr, flush=True)
            return CustomAction.RunResult(success=True)

        best = reco_result.best_result
        if not best:
            return CustomAction.RunResult(success=True)

        recognized_text = best.text if best.text is not None else ""
        full_message = f"{return_text}{recognized_text}"

        # 只输出这一条关键结果到 UI
        print(f"info:{full_message}", file=sys.stderr, flush=True)

        # ---------- 后置操作 ----------
        if click_target:
            do_tap(click_target, hold_after)

        return CustomAction.RunResult(success=True)