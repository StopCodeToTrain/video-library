"""视频库分类工具 - 入口"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def run_gui():
    """启动 GUI 模式"""
    from gui import main as gui_main
    gui_main()


def run_cli():
    """CLI 模式（扫描并分析目录）"""
    import argparse
    from config import get_config

    parser = argparse.ArgumentParser(description="本地视频库分类工具")
    parser.add_argument("--scan", type=str, help="扫描指定目录")
    parser.add_argument("--analyze", action="store_true", help="分析已扫描的视频")
    args = parser.parse_args()

    if args.scan:
        from video_io.scanner import scan_directory
        from storage.database import get_db

        db = get_db()
        config = get_config()
        videos = scan_directory(Path(args.scan), db, config)
        print(f"扫描完成，发现 {len(videos)} 个视频文件")
        db.close()

    elif args.analyze:
        from storage.database import get_db

        db = get_db()
        pending = db.get_videos_by_status("pending")
        if not pending:
            print("没有待分析的视频")
        else:
            print(f"待分析视频: {len(pending)} 个")
            for v in pending:
                print(f"  - {v['file_name']}")
        db.close()

    else:
        parser.print_help()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli()
    else:
        run_gui()
