import subprocess
import re
import sys
import os

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing {' '.join(cmd)}:\n{result.stderr}")
        sys.exit(1)
    return result.stdout

def decompile(dtb_file, dts_file):
    run_cmd(['dtc', '-I', 'dtb', '-O', 'dts', '-o', dts_file, dtb_file])

def compile(dts_file, dtb_file):
    run_cmd(['dtc', '-I', 'dts', '-O', 'dtb', '-o', dtb_file, dts_file])

def extract_block_at(text, start_idx):
    """Extrahiert einen DTS-Block beginnend bei start_idx unter Berücksichtigung verschachtelter Klammern."""
    brace_idx = text.find('{', start_idx)
    if brace_idx == -1:
        return None, -1, -1
    
    open_braces = 0
    in_block = False
    for i in range(brace_idx, len(text)):
        if text[i] == '{':
            open_braces += 1
            in_block = True
        elif text[i] == '}':
            open_braces -= 1
        
        if in_block and open_braces == 0:
            end_idx = i + 1
            if end_idx < len(text) and text[end_idx] == ';':
                end_idx += 1
            return text[start_idx:end_idx], start_idx, end_idx
    return None, -1, -1

def find_node_by_names_or_properties(dts_text, target_names):
    """Sucht flexibel nach Knoten anhand von Namen oder typischen Joystick/Gamepad-Eigenschaften."""
    # 1. Suche nach namentlich bekannten Knoten
    for name in target_names:
        pattern = re.compile(r'([a-zA-Z0-9_-]+:\s*)?' + name + r'(@[0-9a-fA-F]+)?\s*\{')
        match = pattern.search(dts_text)
        if match:
            node_text, start, end = extract_block_at(dts_text, match.start())
            if node_text:
                return node_text, start, end, name

    # 2. Erweiterte Suche über typische Joystick-Eigenschaften im DTS
    if 'abs-range' in dts_text or 'ABS_RX' in dts_text or 'linux,code' in dts_text:
        # Suche nach Vorkommen von abs-range und beame zum Start des übergeordneten Knotens
        for match_iter in re.finditer(r'abs-range', dts_text):
            idx = match_iter.start()
            start = dts_text.rfind('{', 0, idx)
            if start != -1:
                node_start = dts_text.rfind('\n', 0, start) + 1
                node_text, s, e = extract_block_at(dts_text, node_start)
                if node_text and ('axis' in node_text.lower() or 'joystick' in node_text.lower() or 'io-channels' in node_text.lower()):
                    return node_text, node_start, e, "property-matched-joystick"

    return None, -1, -1, None

def main():
    r36t_dtb = 'rk3326-r36tmax-linux.dtb'
    k36s_dtb = 'rk3326-k36s-linux.dtb'
    patched_dts = 'rk3326-k36s-linux-patched.dts'
    patched_dtb = 'rk3326-k36s-linux-patched.dtb'

    if not os.path.exists(r36t_dtb) or not os.path.exists(k36s_dtb):
        print("Fehler: DTB-Dateien nicht gefunden. Bitte sicherstellen, dass rk3326-r36tmax-linux.dtb und rk3326-k36s-linux.dtb im Repo liegen.")
        sys.exit(1)

    print("Dekompiliere DTB-Dateien zu DTS...")
    decompile(r36t_dtb, 'r36t.dts')
    decompile(k36s_dtb, 'k36s.dts')

    with open('r36t.dts', 'r', encoding='utf-8', errors='ignore') as f:
        r36t_text = f.read()
    with open('k36s.dts', 'r', encoding='utf-8', errors='ignore') as f:
        k36s_text = f.read()

    print("Suche nach Joystick/Analogstick-Knoten im R36T Max DTS...")
    target_nodes = [
        'adc-joystick', 
        'joystick', 
        'gamepad', 
        'analog', 
        'saradc-joystick', 
        'rk3326-gamepad', 
        'input-keys',
        'adc_joystick'
    ]
    
    node_text, _, _, found_name = find_node_by_names_or_properties(r36t_text, target_nodes)
    
    if not node_text:
        print("Diagnose - Zeige alle Zeilen mit 'adc', 'axis' oder 'joystick' in r36t.dts:")
        for line in r36t_text.splitlines():
            if any(k in line.lower() for k in ['adc', 'joystick', 'axis', 'saradc', 'gamepad']):
                print("  ->", line.strip())
        print("Fehler: Konnte keinen passenden Analogstick-Knoten in der R36T Max DTS extrahieren.")
        sys.exit(1)
        
    print(f"Analogstick-Knoten erfolgreich gefunden (Erkennungs-Typ: '{found_name}').")

    # Prüfen, ob K36S bereits einen entsprechenden Knoten hat
    _, k36s_start, k36s_end, _ = find_node_by_names_or_properties(k36s_text, target_nodes)
    
    if k36s_start != -1:
        print("Ersetze den bestehenden Joystick-Knoten in der K36S DTS...")
        new_k36s_text = k36s_text[:k36s_start] + node_text + k36s_text[k36s_end:]
    else:
        print("Kein bestehender Joystick-Knoten in K36S DTS gefunden. Füge den Knoten hinzu...")
        last_brace = k36s_text.rfind('}')
        if last_brace != -1:
            new_k36s_text = k36s_text[:last_brace] + '\n\t' + node_text + '\n' + k36s_text[last_brace:]
        else:
            new_k36s_text = k36s_text + '\n' + node_text + '\n'

    with open(patched_dts, 'w', encoding='utf-8') as f:
        f.write(new_k36s_text)

    print("Kompiliere neu gepatchte K36S DTB...")
    compile(patched_dts, patched_dtb)
    print("Erfolg! Die modifizierte DTB-Datei wurde als", patched_dtb, "gespeichert.")

if __name__ == '__main__':
    main()
