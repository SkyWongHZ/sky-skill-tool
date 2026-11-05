#!/usr/bin/env python3
"""Create review drafts in Apple Notes; read existing notes without foregrounding UI."""
import argparse
import html
import json
import subprocess
import tempfile
from pathlib import Path

CREATE = '''on run argv
set accountName to item 1 of argv
set folderName to item 2 of argv
set noteTitle to item 3 of argv
set bodyFile to item 4 of argv
set noteHTML to read (POSIX file bodyFile) as «class utf8»
tell application "Notes"
    set targetAccount to account accountName
    tell targetAccount
        if not (exists folder folderName) then
            make new folder with properties {name:folderName}
        end if
        set targetFolder to folder folderName
    end tell
    tell targetFolder
        set existingNotes to every note whose name is noteTitle
        if (count of existingNotes) > 0 then
            return "EXISTS" & linefeed & id of item 1 of existingNotes
        end if
        set newNote to make new note with properties {name:noteTitle, body:noteHTML}
        return "CREATED" & linefeed & id of newNote
    end tell
end tell
end run'''
READ = '''on run argv
tell application "Notes" to return plaintext of note id (item 1 of argv)
end run'''


def osascript(script, *args):
    with tempfile.NamedTemporaryFile('w', suffix='.applescript') as source:
        source.write(script)
        source.flush()
        result = subprocess.run(['osascript', source.name, *args], capture_output=True,
                                text=True, timeout=30, check=True)
        return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read-id')
    parser.add_argument('--config')
    parser.add_argument('--title')
    parser.add_argument('--file')
    args = parser.parse_args()
    if args.read_id:
        print(osascript(READ, args.read_id))
        return
    if not all([args.config, args.title, args.file]):
        parser.error('--config --title --file are required when creating')
    config = json.loads(Path(args.config).read_text())
    text = Path(args.file).read_text()
    body = '<h1>' + html.escape(args.title) + '</h1>'
    for line in text.splitlines():
        if line.startswith('### '):
            continue
        if line.startswith('#### '):
            body += '<h3>' + html.escape(line[5:]) + '</h3>'
        else:
            body += '<div>' + (html.escape(line) or '<br>') + '</div>'
    with tempfile.NamedTemporaryFile('w', suffix='.html') as rendered:
        rendered.write(body)
        rendered.flush()
        result = osascript(CREATE, config['notes_account'], config['notes_folder'],
                          args.title, rendered.name).splitlines()
    status, note_id = result[0], result[1]
    # Read after writing to verify the note is reachable; never overwrite an existing draft.
    stored = osascript(READ, note_id)
    if status == 'CREATED':
        lines = [line[5:] if line.startswith('#### ') else line for line in text.splitlines()
                 if line.strip() and not line.startswith('### ')]
        if not all(line in stored for line in lines):
            raise RuntimeError(f'Note created but read-back differs; inspect note {note_id} before retry')
    print(json.dumps({'status': status, 'id': note_id, 'title': args.title,
                      'folder': config['notes_folder'], 'readback_verified': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
