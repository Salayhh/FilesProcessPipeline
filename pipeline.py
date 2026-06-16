"""简易运行入口：执行 FilesProcessPipeline 完整流程。"""

from __future__ import annotations

import sys

from files_pipeline.pipeline import PipelineError, run_pipeline


def main() -> int:
    try:
        manifest = run_pipeline()
    except PipelineError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"Pipeline 完成: runs/{manifest.run_id}")
    final_stage = manifest.stages.get("render", {})
    output_files = final_stage.get("output_files", [])
    if output_files:
        print("最终输出:")
        for output_file in output_files:
            print(f"  - runs/{manifest.run_id}/{output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
