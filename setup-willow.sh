#!/usr/bin/env bash
# Willow setup — runs inside WSL Ubuntu on Tyree's PC.
# Called by install.bat. Usage: bash setup-willow.sh [4B-W4|32B]
# 4B-W4 is the pick for the RTX 3090 (24 GB VRAM). 32B needs an 80 GB GPU.
set -euo pipefail

BUILD="${1:-4B-W4}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$HERE/sophon-realtime"

echo "Willow setup — build: $BUILD"
echo "Folder: $HERE"

# --- checks: Python 3.12 ---
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found in WSL. Install Python 3.12 in Ubuntu first."; exit 1; }
echo "Python: $(python3 --version)"
if ! python3 --version 2>&1 | grep -q "3.12"; then
  echo "WARNING: Python is not 3.12. Sophon wants Python 3.12 — the install may fail."
fi
python3 -m pip --version >/dev/null 2>&1 || { echo "ERROR: pip is not installed for Python 3.12. In WSL run: sudo apt update && sudo apt install -y python3-pip python3-venv"; exit 1; }

# --- checks: GPU inside WSL ---
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total --format=csv
else
  echo "NOTE: nvidia-smi not found inside WSL. The GPU install needs NVIDIA drivers that work in WSL."
fi

# --- checks: free disk BEFORE any download ---
# 4B-W4 needs at least 40 GB free (21 GB weights + environment + cache).
# 32B needs at least 80 GB free (45 GB weights + environment + cache).
if [ "$BUILD" = "32B" ]; then NEED_GB=80; else NEED_GB=40; fi
FREE_GB="$(df --output=avail -BG "$HERE" | tail -1 | tr -dc '0-9')"
echo "Free disk here: ${FREE_GB} GB (need at least ${NEED_GB} GB for the $BUILD build)"
if [ "$FREE_GB" -lt "$NEED_GB" ]; then
  echo "ERROR: not enough free disk. Free up space and run install.bat again."
  exit 1
fi
echo "Free system memory: $(free -g | awk '/^Mem:/ {print $7 " GB available"}')"

# --- install ---
if [ "$BUILD" = "32B" ]; then
  echo "Installing 32B Tag with pip (about 42 GB download)..."
  python3 -m pip install --upgrade pip
  python3 -m pip install "sophon-realtime[trt]"
  export PATH="$HOME/.local/bin:$PATH"
  sophon-realtime download
  ROUTE="pip"
  ENGINE_DIR="sophon-realtime/tag"
else
  echo "Installing Tag-4B-W4 with the upstream installer (about 21 GB download)..."
  cd "$REPO/tag"
  SIZE=4B-W4 bash install.sh
  ROUTE="repo"
  ENGINE_DIR="sophon-realtime/tag"
fi

# --- voice folder ---
# The repo route keeps weights in sophon-realtime/tag/model.
# The pip route keeps them in ./model next to this script.
if [ "$ROUTE" = "repo" ]; then VOICES_DIR="$REPO/tag/model/voices"; else VOICES_DIR="$HERE/model/voices"; fi
if [ -d "$(dirname "$VOICES_DIR")" ]; then
  mkdir -p "$VOICES_DIR"
  cat > "$VOICES_DIR/PUT-WILLOW-WAV-HERE.txt" <<'EOF'
Put your voice clip here.
Record 3 to 10 seconds of clean speech, save it as willow.wav,
and copy it into this folder. See VOICE.md in the willow folder.
Until then Willow uses the built-in voice.
EOF
  echo "Voice folder: $VOICES_DIR"
else
  echo "NOTE: model folder not found yet, so the voice folder was not made."
  echo "See VOICE.md for where willow.wav goes once the weights are downloaded."
fi

# --- fetch the voice-activity models if the GitHub copy left them out ---
# The GitHub copy of Sophon leaves out binary files (images, example audio,
# and the silero VAD models). The engine needs the VAD models, so fetch any
# that are missing straight from upstream.
for ONNX in "$REPO/tag/config/silero_vad.onnx" "$REPO/live/sophon_live/silero_vad.onnx"; do
  if [ ! -f "$ONNX" ]; then
    REL="${ONNX#"$REPO"/}"
    echo "Fetching missing $REL from upstream..."
    curl -fL "https://raw.githubusercontent.com/adventists-ai/sophon-realtime/main/$REL" -o "$ONNX"
  fi
done

# --- record what was installed ---
cat > "$HERE/willow-config.txt" <<EOF
BUILD=$BUILD
ROUTE=$ROUTE
ENGINE_DIR=$ENGINE_DIR
PORT=8000
EOF

echo ""
echo "Willow is installed (build $BUILD)."
echo "Next: double-click start-willow.bat, then open talk.html in this folder and press Connect."
echo "Voice: copy a 3-10 second willow.wav into the voices folder (see VOICE.md)."
