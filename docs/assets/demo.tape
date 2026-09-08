# agentseam — hero demo GIF
#
# Renders the real loop: a six-line handler, wired into every coding agent's own hook
# system with one command. The end frame is `agentseam install all`'s real output --
# one line per agent, ending in the enforcement level agentseam actually verified for
# it. No level shown here is claimed beyond what the matrix grades that agent today.
#
# Prerequisites: `agentseam` on PATH (pip install -e .) and VHS
#   (https://github.com/charmbracelet/vhs)
# Render:
#   vhs docs/assets/demo.tape        # writes docs/assets/demo.gif

Output docs/assets/demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 640
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set Padding 24

# --- hidden setup: throwaway repo, throwaway HOME (junie/kimi_code write under $HOME) ---
Hide
Type "cd $(mktemp -d) && git init -q && export HOME=$(mktemp -d) && clear"
Enter
Type "echo ZnJvbSBhZ2VudHNlYW0gaW1wb3J0IHJ1biwgRGVjaXNpb24KCmRlZiBoYW5kbGVyKGV2ZW50KToKICAgIGlmIGV2ZW50LmV2ZW50ID09ICJwcmVfdG9vbCIgYW5kICJBS0lBIiBpbiAoZXZlbnQuY29udGVudCBvciAiIik6CiAgICAgICAgcmV0dXJuIERlY2lzaW9uLmRlbnkoIm5vIEFXUyBrZXlzIGluIG1lbW9yeSBmaWxlcyIpCiAgICByZXR1cm4gRGVjaXNpb24uYWxsb3coKQoKcnVuKGhhbmRsZXIpCg== | base64 -d > my_handler.py && clear"
Enter
Show

# --- 1. the handler is six lines ---
Type "cat my_handler.py"
Enter
Sleep 2500ms

# --- 2. wire it into every agent at once; end frame holds the real per-agent levels ---
Type 'agentseam install all "python3 my_handler.py" --events pre_tool'
Enter
Sleep 4000ms
