#!/bin/bash
# ============================================================
# setup_keyless_ssh.sh — 免密 SSH + 建别名（Windows/git-bash，无 sshpass）
# 用法: bash setup_keyless_ssh.sh <PORT> <HOSTNAME> <PASSWORD> <ALIAS> [PUBKEY]
#   PORT      SSH 端口
#   HOSTNAME  connect.xxx.seetacloud.com
#   PASSWORD  root 密码（首次装钥用，之后不需要）
#   ALIAS     ~/.ssh/config 里的 Host 别名（如 autodl-qwen-clone1）
#   PUBKEY    本地公钥路径，默认 ~/.ssh/id_rsa_musetalk.pub
# 前置：本地有 ~/.ssh/id_rsa_musetalk(.pub)。DNS 名可含 [ ]。
# ============================================================
set -euo pipefail
PORT="${1:?用法: $0 <PORT> <HOSTNAME> <PASSWORD> <ALIAS> [PUBKEY]}"
HOSTNAME="${2:?}"
PASSWORD="${3:?}"
ALIAS="${4:?}"
PUBKEY="${5:-$HOME/.ssh/id_rsa_musetalk.pub}"
KEYPRIV="${PUBKEY%.pub}"

# 检查公钥
[ -f "$PUBKEY" ] || { echo "❌ 公钥不存在: $PUBKEY"; exit 1; }
[ -f "$KEYPRIV" ] || KEYPRIV="$HOME/.ssh/id_rsa_musetalk"

# 备份 config
[ -f "$HOME/.ssh/config" ] && cp "$HOME/.ssh/config" "$HOME/.ssh/config.bak.qwenclone"

# 1) 用 SSH_ASKPASS 密码注入装公钥
ASKPASS="$(mktemp /tmp/askpass.XXXXXX)"
printf '#!/bin/bash\necho "%s"\n' "$PASSWORD" > "$ASKPASS"
chmod +x "$ASKPASS"
echo ">>> 装公钥到 ${HOSTNAME}:${PORT} ..."
SSH_ASKPASS="$ASKPASS" SSH_ASKPASS_REQUIRE=force DISPLAY=:0 \
  ssh -p "$PORT" -o StrictHostKeyChecking=no -o NumberOfPasswordPrompts=1 \
  "root@$HOSTNAME" \
  "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh && echo PUBKEY_OK" \
  < "$PUBKEY" 2>&1 | tail -1
rm -f "$ASKPASS"

# 2) 验证免密（必须带 -i 私钥，否则 BatchMode 用默认 key 失败）
echo ">>> 验证免密 ..."
if ssh -p "$PORT" -o BatchMode=yes -i "$KEYPRIV" "root@$HOSTNAME" 'echo KEYLESS_OK' 2>&1 | grep -q KEYLESS_OK; then
  echo "✅ 免密成功"
else
  echo "❌ 免密失败（试试检查 authorized_keys 或私钥匹配）"; exit 1
fi

# 3) 写/改别名到 ~/.ssh/config
if grep -q "^Host $ALIAS[[:space:]]*$" "$HOME/.ssh/config" 2>/dev/null; then
  echo "ℹ️  别名 $ALIAS 已存在，改端口"
  # 用 perl 精准替换该 Host 块 Port 行（简单起见用 python）
  python - "$ALIAS" "$HOSTNAME" "$PORT" "$KEYPRIV" <<'PY'
import sys,re
alias,host,port,key=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
p=__import__('os').path.expanduser('~/.ssh/config')
lines=open(p,encoding='utf-8').read().splitlines(True)
out=[]; i=0; inblock=False; found=False
while i<len(lines):
    l=lines[i]
    out.append(l)
    if re.match(rf'^Host\s+{re.escape(alias)}\s*$', l.strip()):
        inblock=True; found=True; i+=1
        while i<len(lines) and (lines[i].startswith(' ') or lines[i].startswith('\t')):
            if re.match(r'^\s*HostName\s', lines[i]): out.append(f'    HostName {host}\n')
            elif re.match(r'^\s*Port\s', lines[i]): out.append(f'    Port {port}\n')
            elif re.match(r'^\s*IdentityFile\s', lines[i]): out.append(f'    IdentityFile {key}\n')
            elif re.match(r'^\s*User\s', lines[i]): out.append(f'    User root\n')
            else: out.append(lines[i])
            i+=1
        continue
    i+=1
if not found:
    out.append(f'\n# Qwen3.8 clone ({host})\nHost {alias}\n    HostName {host}\n    Port {port}\n    User root\n    IdentityFile {key}\n    ServerAliveInterval 60\n    ServerAliveCountMax 3\n')
open(p,'w',encoding='utf-8').write(''.join(out))
print('✅ config 已更新' if found else '✅ config 已追加')
PY
else
  cat >> "$HOME/.ssh/config" <<EOF

# Qwen3.8 clone (${HOSTNAME})
Host ${ALIAS}
    HostName ${HOSTNAME}
    Port ${PORT}
    User root
    IdentityFile ${KEYPRIV}
    ServerAliveInterval 60
    ServerAliveCountMax 3
EOF
  echo "✅ config 已追加"
fi

# 4) 再验证别名
ssh -o BatchMode=yes "$ALIAS" 'echo "✅ 别名可用: '"$ALIAS"'"' 2>&1 | tail -1