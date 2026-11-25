import argparse
import json
import os
import sys
from pathlib import Path

from living_library.adapters import chatgpt_export, claude_export, gemini_export
from living_library.api import run_api
from living_library.db import connect, get_conversation, get_default_db_path, init_db
from living_library.ingest import save_conversation, save_session
from living_library.mcp_server import run_mcp
from living_library.reembed import reembed_store
from living_library.resummarize import resummarize_store
from living_library.titlers import retitle_store


def cmd_init(args):
    path = args.db_path or get_default_db_path()
    init_db(str(path))
    print(f'Initialized database at {path}')


def cmd_save(args):
    full_log = Path(args.file).read_text(encoding='utf-8')
    conn = connect()
    save_conversation(conn, full_log, title=args.title, source=args.source)
    conn.close()
    print('Saved.')


def cmd_search(args):
    from living_library.search import search

    conn = connect()
    results = search(conn, args.query, args.limit)
    conn.close()
    for row in results:
        print(f'{row["id"]}: {row["title"]}')


def cmd_show(args):
    conn = connect()
    row = get_conversation(conn, args.conversation_id)
    conn.close()
    if row:
        print(row['full_log'])
    else:
        print('Conversation not found.')


def cmd_import(args):
    adapters = {'claude': claude_export, 'gemini': gemini_export, 'chatgpt': chatgpt_export}
    rows = adapters[args.provider](str(args.file))
    conn = connect()
    count = 0
    for row in rows:
        if not row['full_log']:
            continue
        save_conversation(
            conn,
            row['full_log'],
            title=row.get('title'),
            source=row.get('source'),
        )
        count += 1
    conn.close()
    print(f'Imported {count} conversations')


def cmd_reembed(args):
    if not args.yes:
        answer = input('Re-embed all conversations? [y/N]: ')
        if answer.lower() != 'y':
            print('Aborted.')
            return
    conn = connect()
    reembed_store(conn)
    conn.close()
    print('Re-embedded conversations.')


def cmd_resummarize(args):
    if args.empty and args.all:
        raise SystemExit('Choose either --empty or --all')
    conn = connect()
    resummarize_store(conn, empty_only=not args.all)
    conn.close()
    print('Resummarized conversations.')


def cmd_retitle(args):
    conn = connect()
    retitle_store(conn, all_rows=args.all)
    conn.close()
    print('Retitled conversations.')


def cmd_serve_api(args):
    run_api(args.host, args.port, args.reload)


def cmd_serve_mcp(args):
    run_mcp()


def cmd_claude_hook(args):
    payload_text = sys.stdin.read()
    payload = {}
    transcript_path = None
    try:
        payload = json.loads(payload_text)
        transcript_path = payload.get('transcript_path')
    except json.JSONDecodeError:
        stdin_name = getattr(sys.stdin, 'name', '')
        if stdin_name and stdin_name not in ('<stdin>', ''):
            transcript_path = stdin_name

    if not transcript_path:
        print('Missing transcript_path.')
        return

    from living_library.adapters import claude_transcript_to_log

    full_log = claude_transcript_to_log(transcript_path)
    minimum = int(os.environ.get('LIVING_LIBRARY_MIN_SESSION_CHARS', '200'))
    if len(full_log.replace(' ', '').replace('\n', '')) < minimum:
        print('Session too short.')
        return

    session_id = payload.get('session_id') if payload else None
    if not session_id:
        session_id = os.environ.get('CLAUDE_SESSION_ID')
    if not session_id:
        print('Missing session_id.')
        return

    conn = connect()
    policy = os.environ.get('LIVING_LIBRARY_SUMMARY_POLICY', 'each_turn')
    existing = get_conversation(conn, session_id=session_id)
    try:
        if policy == 'session_end' and existing is None:
            save_session(
                conn,
                session_id,
                full_log,
                source='claude-code',
                summary_override='',
                summarizer_override='extractive',
            )
        elif policy == 'session_end' and payload.get('hook_event_name') in (None, 'SessionEnd'):
            save_session(
                conn,
                session_id,
                full_log,
                source='claude-code',
            )
        elif policy == 'session_end':
            save_session(
                conn,
                session_id,
                full_log,
                source='claude-code',
                summary_override='',
                summarizer_override='extractive',
            )
        else:
            save_session(
                conn,
                session_id,
                full_log,
                source='claude-code',
            )
    except RuntimeError:
        save_session(
            conn,
            session_id,
            full_log,
            source='claude-code',
            summary_override='',
            summarizer_override='extractive',
        )
    conn.commit()
    conn.close()
    print('Saved session.')


def build_parser():
    parser = argparse.ArgumentParser(prog='living-library')
    sub = parser.add_subparsers(dest='command', required=True)

    init = sub.add_parser('init')
    init.add_argument('--db-path', type=Path)
    init.set_defaults(handler=cmd_init)

    save = sub.add_parser('save')
    save.add_argument('file')
    save.add_argument('--title')
    save.add_argument('--source', default='local')
    save.set_defaults(handler=cmd_save)

    search = sub.add_parser('search')
    search.add_argument('query')
    search.add_argument('--limit', type=int, default=5)
    search.set_defaults(handler=cmd_search)

    show = sub.add_parser('show')
    show.add_argument('conversation_id', type=int)
    show.set_defaults(handler=cmd_show)

    import_parser = sub.add_parser('import')
    import_parser.add_argument('provider', choices=('claude', 'gemini', 'chatgpt'))
    import_parser.add_argument('file')
    import_parser.set_defaults(handler=cmd_import)

    reembed = sub.add_parser('reembed')
    reembed.add_argument('--yes', action='store_true')
    reembed.set_defaults(handler=cmd_reembed)

    resummarize = sub.add_parser('resummarize')
    resummarize.add_argument('--empty', action='store_true')
    resummarize.add_argument('--all', action='store_true')
    resummarize.add_argument('--yes', action='store_true')
    resummarize.set_defaults(handler=cmd_resummarize)

    retitle = sub.add_parser('retitle')
    retitle.add_argument('--all', action='store_true')
    retitle.add_argument('--yes', action='store_true')
    retitle.set_defaults(handler=cmd_retitle)

    api = sub.add_parser('serve_api', aliases=['serve-api'])
    api.add_argument('--host', default='127.0.0.1')
    api.add_argument('--port', type=int, default=8000)
    api.add_argument('--reload', action='store_true')
    api.set_defaults(handler=cmd_serve_api)

    mcp = sub.add_parser('serve_mcp', aliases=['serve-mcp'])
    mcp.set_defaults(handler=cmd_serve_mcp)

    hook = sub.add_parser('claude-hook')
    hook.set_defaults(handler=cmd_claude_hook)
    return parser


def main():
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == '__main__':
    main()
