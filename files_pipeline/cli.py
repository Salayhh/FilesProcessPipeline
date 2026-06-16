"""Command line interface for FilesProcessPipeline v2."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from files_pipeline.pipeline import PipelineError, archive_run, run_organize, run_parse, run_pipeline, run_render


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="files-pipeline", description="文档结构化处理 Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="执行完整流程")
    run_parser.add_argument("--input", default="input", help="输入目录，默认 input")
    run_parser.add_argument("--run-id", default=None, help="指定运行 ID")

    parse_parser = subparsers.add_parser("parse", help="只执行 MinerU 解析")
    parse_parser.add_argument("--input", default="input", help="输入目录，默认 input")
    parse_parser.add_argument("--run-id", default=None, help="指定运行 ID")

    organize_parser = subparsers.add_parser("organize", help="只执行 Kimi 整理")
    organize_parser.add_argument("--run-id", required=True, help="已有运行 ID")

    render_parser = subparsers.add_parser("render", help="只执行最终渲染")
    render_parser.add_argument("--run-id", required=True, help="已有运行 ID")

    archive_parser = subparsers.add_parser("archive", help="显式归档一个运行目录")
    archive_parser.add_argument("--run-id", required=True, help="要归档的运行 ID")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            manifest = run_pipeline(input_dir=Path(args.input), run_id=args.run_id)
            print_success(manifest.run_id, "完整流程完成")
        elif args.command == "parse":
            manifest = run_parse(input_dir=Path(args.input), run_id=args.run_id)
            print_success(manifest.run_id, "MinerU 解析完成")
        elif args.command == "organize":
            manifest = run_organize(args.run_id)
            print_success(manifest.run_id, "Kimi 整理完成")
        elif args.command == "render":
            manifest = run_render(args.run_id)
            print_success(manifest.run_id, "最终渲染完成")
        elif args.command == "archive":
            target = archive_run(args.run_id)
            print(f"归档完成: {target}")
        return 0
    except PipelineError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


def print_success(run_id: str, message: str) -> None:
    print(f"{message}: runs/{run_id}")


if __name__ == "__main__":
    sys.exit(main())
