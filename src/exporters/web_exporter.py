"""
Web Exporter Module
Exports tutorials to HTML, iframe embed, and Lottie animation formats
"""
import os
import json
import base64
from typing import Callable, Optional
from ..model import Tutorial, Step


class WebExporter:
    """Export tutorial to web-friendly formats."""
    
    def __init__(self, tutorial: Tutorial, progress_callback: Optional[Callable[[int], None]] = None):
        self.tutorial = tutorial
        self.progress_callback = progress_callback
    
    def export_html(self, output_path: str, embed_images: bool = True) -> bool:
        """Export as standalone HTML webpage with interactive tutorial."""
        import cv2
        
        # Prepare step data and images
        steps_data = []
        for i, step in enumerate(self.tutorial.steps):
            step_info = {
                'index': i + 1,
                'description': step.description,
                'instruction': step.instruction,
                'action_type': step.action_type,
                'x': step.x,
                'y': step.y,
                'width': step.width,
                'height': step.height,
                'shape': step.shape,
                'keyboard_mode': step.keyboard_mode,
                'keyboard_input': step.keyboard_input,
                'image': ''
            }
            
            # Get image
            img = None
            if step.image_path and os.path.exists(step.image_path):
                img = cv2.imread(step.image_path)
            elif self.tutorial.video_path and os.path.exists(self.tutorial.video_path):
                cap = cv2.VideoCapture(self.tutorial.video_path)
                fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(step.timestamp * fps))
                ret, img = cap.read()
                cap.release()
            
            if img is not None and embed_images:
                _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                step_info['image'] = 'data:image/jpeg;base64,' + base64.b64encode(buffer).decode()
            
            steps_data.append(step_info)
            
            if self.progress_callback:
                self.progress_callback(int((i + 1) / len(self.tutorial.steps) * 50))
        
        html_content = self._generate_html(steps_data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        if self.progress_callback:
            self.progress_callback(100)
        
        print(f"Exported HTML to: {output_path}")
        return True
    
    def _generate_html(self, steps_data: list) -> str:
        """Generate interactive HTML content matching Play mode."""
        steps_json = json.dumps(steps_data)
        
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.tutorial.title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
            min-height: 100vh;
            color: white;
            overflow: hidden;
        }}
        
        /* Progress Bar */
        .progress-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
            background: rgba(255,255,255,0.1);
            z-index: 1000;
        }}
        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5, #9333ea);
            transition: width 0.5s ease;
            box-shadow: 0 0 20px rgba(0, 210, 255, 0.5);
        }}
        
        /* Header */
        .header {{
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.7);
            padding: 10px 30px;
            border-radius: 30px;
            backdrop-filter: blur(10px);
            z-index: 100;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        .step-badge {{
            background: linear-gradient(135deg, #ff6b6b, #ff8e53);
            width: 35px;
            height: 35px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
        }}
        .step-desc {{
            font-size: 1.1em;
        }}
        .step-instruction {{
            font-size: 0.9em;
            color: #aaa;
            margin-top: 5px;
            max-width: 500px;
        }}
        
        /* Main Canvas Area */
        .canvas-container {{
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            position: relative;
            cursor: grab;
        }}
        .canvas-container:active {{
            cursor: grabbing;
        }}
        .canvas-inner {{
            position: absolute;
            transform-origin: 0 0;
            transition: transform 0.1s ease-out;
        }}
        .step-image {{
            display: block;
            user-select: none;
            -webkit-user-drag: none;
        }}
        
        /* Hitbox Overlay */
        .hitbox {{
            position: absolute;
            border: 3px solid #ff4444;
            cursor: pointer;
            transition: all 0.3s ease;
            animation: pulse 1.5s infinite, glow 1.5s infinite;
        }}
        .hitbox:hover {{
            transform: scale(1.05);
            border-color: #ffff00;
        }}
        .hitbox.circle {{
            border-radius: 50%;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); }}
            50% {{ transform: scale(1.03); }}
        }}
        
        @keyframes glow {{
            0%, 100% {{ 
                box-shadow: 0 0 10px rgba(255, 68, 68, 0.5), 
                            0 0 20px rgba(255, 68, 68, 0.3),
                            0 0 30px rgba(255, 68, 68, 0.2);
            }}
            50% {{ 
                box-shadow: 0 0 20px rgba(255, 68, 68, 0.8), 
                            0 0 40px rgba(255, 68, 68, 0.5),
                            0 0 60px rgba(255, 68, 68, 0.3);
            }}
        }}
        
        /* Keyboard Input Modal */
        .modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: transparent;
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 500;
        }}
        .modal-overlay.active {{
            display: flex;
        }}
        .modal-content {{
            background: linear-gradient(145deg, #1e1e2e, #2a2a3e);
            padding: 40px;
            border-radius: 20px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .modal-title {{
            font-size: 1.5em;
            margin-bottom: 10px;
            color: #00d2ff;
        }}
        .modal-hint {{
            color: #888;
            margin-bottom: 20px;
        }}
        .modal-input {{
            width: 300px;
            padding: 15px 20px;
            font-size: 1.2em;
            border: 2px solid #444;
            border-radius: 10px;
            background: #1a1a2e;
            color: white;
            text-align: center;
            outline: none;
            transition: border-color 0.3s;
            position: relative;
            z-index: 2;
        }}
        .modal-input-wrap {{
            position: relative;
            width: 300px;
            margin: 0 auto;
        }}
        .modal-input-ghost {{
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: rgba(255, 255, 255, 0.45);
            pointer-events: none;
            font-size: 1.2em;
            padding: 15px 20px;
            z-index: 3;
        }}
        .modal-input:focus {{
            border-color: #00d2ff;
        }}
        .modal-input.error {{
            border-color: #ff4444;
            animation: shake 0.3s;
        }}
        .modal-input.success {{
            border-color: #4CAF50;
        }}
        
        @keyframes shake {{
            0%, 100% {{ transform: translateX(0); }}
            25% {{ transform: translateX(-10px); }}
            75% {{ transform: translateX(10px); }}
        }}
        
        /* Zoom Controls */
        .zoom-controls {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 100;
        }}
        .zoom-btn {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            border: none;
            background: rgba(0,0,0,0.7);
            color: white;
            font-size: 1.5em;
            cursor: pointer;
            transition: all 0.2s;
            backdrop-filter: blur(10px);
        }}
        .zoom-btn:hover {{
            background: rgba(0,150,255,0.7);
            transform: scale(1.1);
        }}
        
        /* Start/Completion Screen */
        .screen-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            transition: opacity 0.5s;
        }}
        .screen-overlay.hidden {{
            opacity: 0;
            pointer-events: none;
        }}
        .screen-title {{
            font-size: 3em;
            margin-bottom: 20px;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .screen-subtitle {{
            font-size: 1.3em;
            color: #888;
            margin-bottom: 40px;
        }}
        .screen-btn {{
            padding: 20px 60px;
            font-size: 1.3em;
            border: none;
            border-radius: 50px;
            background: linear-gradient(135deg, #00d2ff, #3a7bd5);
            color: white;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 10px 30px rgba(0, 210, 255, 0.3);
        }}
        .screen-btn:hover {{
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(0, 210, 255, 0.4);
        }}
        .completion-icon {{
            font-size: 5em;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <!-- Progress Bar -->
    <div class="progress-container">
        <div class="progress-bar" id="progressBar"></div>
    </div>
    
    <!-- Header -->
    <div class="header" id="header">
        <div class="step-badge" id="stepBadge">1</div>
        <div>
            <div class="step-desc" id="stepDesc">Loading...</div>
            <div class="step-instruction" id="stepInstruction"></div>
        </div>
    </div>
    
    <!-- Main Canvas -->
    <div class="canvas-container" id="canvasContainer">
        <div class="canvas-inner" id="canvasInner">
            <img class="step-image" id="stepImage" src="" alt="">
            <div class="hitbox" id="hitbox"></div>
        </div>
    </div>
    
    <!-- Keyboard Modal -->
    <div class="modal-overlay" id="keyboardModal">
        <div class="modal-content">
            <div class="modal-title">⌨️ Type the required text</div>
            <div class="modal-hint" id="modalHint">Enter the text shown below</div>
            <div class="modal-input-wrap" id="modalInputWrap">
                <input type="text" class="modal-input" id="modalInput" autocomplete="off">
                <div class="modal-input-ghost" id="modalInputGhost"></div>
            </div>
        </div>
    </div>
    
    <!-- Zoom Controls -->
    <div class="zoom-controls">
        <button class="zoom-btn" onclick="zoomIn()">+</button>
        <button class="zoom-btn" onclick="zoomOut()">−</button>
        <button class="zoom-btn" onclick="resetZoom()">⟲</button>
    </div>
    
    <!-- Start Screen -->
    <div class="screen-overlay" id="startScreen">
        <div class="screen-title">{self.tutorial.title}</div>
        <div class="screen-subtitle">Interactive Tutorial</div>
        <button class="screen-btn" id="startBtn" onclick="startTutorial()">▶ Start</button>
    </div>
    
    <!-- Completion Screen -->
    <div class="screen-overlay hidden" id="completionScreen">
        <div class="completion-icon">🎉</div>
        <div class="screen-title">Tutorial Complete!</div>
        <div class="screen-subtitle">Great job! You've completed all steps.</div>
        <button class="screen-btn" onclick="restartTutorial()">🔄 Restart</button>
    </div>
    
    <script>
        const steps = {steps_json};
        let currentStep = 0;
        let scale = 1;
        let panX = 0, panY = 0;
        let isDragging = false;
        let dragStart = {{x: 0, y: 0}};
        let hasStarted = false;
        
        const canvasContainer = document.getElementById('canvasContainer');
        const canvasInner = document.getElementById('canvasInner');
        const stepImage = document.getElementById('stepImage');
        const hitbox = document.getElementById('hitbox');
        const keyboardModal = document.getElementById('keyboardModal');
        const modalInput = document.getElementById('modalInput');
        const modalHint = document.getElementById('modalHint');
        const modalInputGhost = document.getElementById('modalInputGhost');
        const modalInputWrap = document.getElementById('modalInputWrap');
        
        // Initialize
        function init() {{
            setupPanZoom();
            preloadImages();
        }}
        
        function preloadImages() {{
            steps.forEach(step => {{
                const img = new Image();
                img.src = step.image;
            }});
        }}
        
        function startTutorial() {{
            hasStarted = true;
            document.getElementById('startScreen').classList.add('hidden');
            document.getElementById('startBtn').textContent = '🔄 Restart';
            renderStep(0);
        }}
        
        function restartTutorial() {{
            currentStep = 0;
            document.getElementById('completionScreen').classList.add('hidden');
            renderStep(0);
        }}
        
        function renderStep(index) {{
            if (index >= steps.length) {{
                showCompletion();
                return;
            }}
            
            const step = steps[index];
            currentStep = index;
            
            // Update header
            document.getElementById('stepBadge').textContent = step.index;
            document.getElementById('stepDesc').textContent = step.description;
            document.getElementById('stepInstruction').textContent = step.instruction || '';
            
            // Update progress
            document.getElementById('progressBar').style.width = ((index + 1) / steps.length * 100) + '%';
            
            // Update image with onload handler for fit
            stepImage.onload = function() {{
                fitToWindow();
                updateHitbox(step);
            }};
            stepImage.src = step.image;
        }}
        
        function updateHitbox(step) {{
            // Update hitbox after image is loaded and fitted
            // Hitbox is INSIDE canvasInner which has CSS transform, so use ORIGINAL coordinates
            if (step.action_type === 'keyboard') {{
                hitbox.style.display = 'none';
                showKeyboardModal(step);
            }} else {{
                hideKeyboardModal();
                hitbox.style.display = 'block';
                
                // Use original coordinates - CSS transform on canvasInner handles scaling
                hitbox.style.left = step.x + 'px';
                hitbox.style.top = step.y + 'px';
                hitbox.style.width = step.width + 'px';
                hitbox.style.height = step.height + 'px';
                hitbox.className = 'hitbox' + (step.shape === 'circle' ? ' circle' : '');
                hitbox.style.background = 'rgba(255, 68, 68, 0.3)';
            }}
        }}
        
        function showKeyboardModal(step) {{
            keyboardModal.classList.add('active');
            modalInput.value = '';
            modalInput.className = 'modal-input';
            document.onkeydown = null;
            const customInstruction = (step.instruction || '').trim();
            
            let expectedInput = step.keyboard_input.toLowerCase().trim();
            if (expectedInput.startsWith('key.')) expectedInput = expectedInput.substring(4);
            
            const keyAliases = {{
                'escape': 'esc',
                'return': 'enter',
                'del': 'delete',
                'arrowup': 'up',
                'arrowdown': 'down',
                'arrowleft': 'left',
                'arrowright': 'right',
                'page_up': 'pageup',
                'page_down': 'pagedown'
            }};
            expectedInput = keyAliases[expectedInput] || expectedInput;
            
            const specialKeys = ['delete', 'backspace', 'tab', 'esc', 'enter', 'space',
                'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown',
                'insert', 'capslock', 'numlock', 'scrolllock', 'pause', 'printscreen',
                'ctrl', 'alt', 'shift', 'cmd'];
            const isFkey = expectedInput.startsWith('f') && expectedInput.length > 1 && !isNaN(expectedInput.substring(1));
            const inferredSpecial = specialKeys.includes(expectedInput) || isFkey;
            const isSpecial = (step.keyboard_mode || '') === 'key' || inferredSpecial;
            
            if (isSpecial) {{
                modalHint.textContent = customInstruction || `Press: ${{step.keyboard_input}}`;
                modalHint.style.display = 'block';
                modalInput.style.display = 'none';
                modalInputWrap.style.display = 'none';
                modalInputGhost.textContent = '';
            }} else {{
                modalHint.textContent = customInstruction || '';
                modalHint.style.display = customInstruction ? 'block' : 'none';
                modalInput.style.display = 'block';
                modalInputWrap.style.display = 'block';
                modalInputGhost.textContent = step.keyboard_input;
                modalInput.focus();
            }}
            
            document.onkeydown = function(e) {{
                let keyName = e.key.toLowerCase();
                
                if (e.key === 'Delete') keyName = 'delete';
                else if (e.key === 'Backspace') keyName = 'backspace';
                else if (e.key === 'Tab') keyName = 'tab';
                else if (e.key === 'Escape') keyName = 'esc';
                else if (e.key === 'Enter') keyName = 'enter';
                else if (e.key === ' ') keyName = 'space';
                else if (e.key === 'ArrowUp') keyName = 'up';
                else if (e.key === 'ArrowDown') keyName = 'down';
                else if (e.key === 'ArrowLeft') keyName = 'left';
                else if (e.key === 'ArrowRight') keyName = 'right';
                else if (e.key === 'Home') keyName = 'home';
                else if (e.key === 'End') keyName = 'end';
                else if (e.key === 'PageUp') keyName = 'pageup';
                else if (e.key === 'PageDown') keyName = 'pagedown';
                else if (e.key === 'Insert') keyName = 'insert';
                else if (e.key.startsWith('F') && e.key.length > 1) keyName = e.key.toLowerCase();

                if (isSpecial) {{
                    if (keyName === expectedInput) {{
                        e.preventDefault();
                        modalInput.className = 'modal-input success';
                        setTimeout(() => {{
                            hideKeyboardModal();
                            nextStep();
                        }}, 200);
                    }}
                    return;
                }}
                
                if (e.key === 'Enter' || e.key === ' ') {{
                    e.preventDefault();
                    if (modalInput.value === step.keyboard_input) {{
                        modalInput.className = 'modal-input success';
                        document.onkeydown = null;
                        setTimeout(() => {{
                            hideKeyboardModal();
                            nextStep();
                        }}, 300);
                    }} else {{
                        modalInput.className = 'modal-input error';
                        setTimeout(() => modalInput.className = 'modal-input', 300);
                    }}
                }}
            }};
        }}
        
        function hideKeyboardModal() {{
            document.onkeydown = null;
            keyboardModal.classList.remove('active');
        }}

        modalInput.addEventListener('input', function() {{
            modalInputGhost.style.display = modalInput.value ? 'none' : 'flex';
        }});
        
        function nextStep() {{
            renderStep(currentStep + 1);
        }}
        
        function showCompletion() {{
            document.getElementById('completionScreen').classList.remove('hidden');
            document.getElementById('progressBar').style.width = '100%';
        }}
        
        // Hitbox click
        hitbox.addEventListener('click', function(e) {{
            e.stopPropagation();
            this.style.background = 'rgba(0, 255, 0, 0.5)';
            setTimeout(() => nextStep(), 200);
        }});
        
        // Pan & Zoom
        function setupPanZoom() {{
            canvasContainer.addEventListener('wheel', function(e) {{
                e.preventDefault();
                const delta = e.deltaY > 0 ? -0.1 : 0.1;
                scale = Math.min(Math.max(0.3, scale + delta), 3);
                updateTransform();
            }});
            
            canvasContainer.addEventListener('mousedown', function(e) {{
                if (e.target === hitbox) return;
                isDragging = true;
                dragStart = {{x: e.clientX - panX, y: e.clientY - panY}};
                canvasContainer.style.cursor = 'grabbing';
            }});
            
            document.addEventListener('mousemove', function(e) {{
                if (!isDragging) return;
                panX = e.clientX - dragStart.x;
                panY = e.clientY - dragStart.y;
                updateTransform();
            }});
            
            document.addEventListener('mouseup', function() {{
                isDragging = false;
                canvasContainer.style.cursor = 'grab';
            }});
            
            window.addEventListener('resize', fitToWindow);
        }}
        
        function updateTransform() {{
            canvasInner.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
        }}
        
        function fitToWindow() {{
            // Get viewport dimensions
            const viewW = window.innerWidth;
            const viewH = window.innerHeight - 80; // Account for header
            
            // Get image native dimensions
            const imgW = stepImage.naturalWidth || 1920;
            const imgH = stepImage.naturalHeight || 1080;
            
            // Calculate scale to fit
            const scaleX = viewW / imgW;
            const scaleY = viewH / imgH;
            scale = Math.min(scaleX, scaleY, 1); // Don't scale above 100%
            
            // Center the image
            const scaledW = imgW * scale;
            const scaledH = imgH * scale;
            panX = (viewW - scaledW) / 2;
            panY = (viewH - scaledH) / 2 + 40; // Offset for header
            
            updateTransform();
        }}
        
        function zoomIn() {{
            scale = Math.min(scale * 1.25, 3);
            updateTransform();
        }}
        
        function zoomOut() {{
            scale = Math.max(scale / 1.25, 0.3);
            updateTransform();
        }}
        
        function resetZoom() {{
            fitToWindow();
        }}
        
        init();
    </script>
</body>
</html>'''

    
    def export_iframe_embed(self, output_path: str) -> bool:
        """Export as embeddable iframe/JavaScript widget."""
        # First export HTML
        html_path = output_path.replace('.js', '.html')
        self.export_html(html_path, embed_images=True)
        
        # Create JavaScript embed code
        js_content = f'''// TutoMake Embed Widget
// Usage: <div id="tutomake-widget"></div><script src="{os.path.basename(output_path)}"></script>
(function() {{
    var container = document.getElementById('tutomake-widget');
    if (!container) {{
        console.error('TutoMake: Container element #tutomake-widget not found');
        return;
    }}
    
    var iframe = document.createElement('iframe');
    iframe.src = '{os.path.basename(html_path)}';
    iframe.style.width = '100%';
    iframe.style.height = '600px';
    iframe.style.border = 'none';
    iframe.style.borderRadius = '10px';
    iframe.style.boxShadow = '0 10px 40px rgba(0,0,0,0.2)';
    
    container.appendChild(iframe);
}})();
'''
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
        
        print(f"Exported iframe embed to: {output_path}")
        return True
    
    def export_lottie(self, output_path: str) -> bool:
        """Export as Lottie JSON animation (simplified version)."""
        # Create a simplified Lottie animation
        animation = {
            "v": "5.7.4",
            "fr": 24,
            "ip": 0,
            "op": len(self.tutorial.steps) * 48,  # 2 seconds per step
            "w": 1920,
            "h": 1080,
            "nm": self.tutorial.title,
            "ddd": 0,
            "assets": [],
            "layers": []
        }
        
        # Add a simple marker layer for each step
        for i, step in enumerate(self.tutorial.steps):
            layer = {
                "ddd": 0,
                "ind": i + 1,
                "ty": 4,  # Shape layer
                "nm": f"Step {i + 1}",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "p": {"a": 0, "k": [step.x + step.width/2, step.y + step.height/2, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "ip": i * 48,
                "op": (i + 1) * 48,
                "st": i * 48
            }
            animation["layers"].append(layer)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(animation, f, indent=2)
        
        print(f"Exported Lottie to: {output_path}")
        return True
    
    def export_video_html(self, output_path: str) -> bool:
        """Export as HTML with embedded video playback and interactive hitboxes."""
        import shutil
        
        if not self.tutorial.video_path or not os.path.exists(self.tutorial.video_path):
            print("No video file found for video HTML export")
            return False
        
        # Get output directory - use current directory if none specified
        output_dir = os.path.dirname(output_path)
        if not output_dir:
            output_dir = os.getcwd()
        
        video_basename = "tutorial_video.mp4"
        video_output = os.path.join(output_dir, video_basename)
        
        print(f"Video source: {self.tutorial.video_path}")
        print(f"Video output: {video_output}")
        
        try:
            # Try to convert with imageio-ffmpeg for H.264 compatibility
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            import subprocess
            
            print("Converting video to H.264...")
            result = subprocess.run([
                ffmpeg_path, '-y', '-i', self.tutorial.video_path,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                video_output
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                # Fallback: just copy the file
                shutil.copy2(self.tutorial.video_path, video_output)
                print("Copied original video instead")
        except Exception as e:
            print(f"Video conversion failed, copying original: {e}")
            shutil.copy2(self.tutorial.video_path, video_output)
        
        # Prepare step data
        steps_data = []
        for i, step in enumerate(self.tutorial.steps):
            step_info = {
                'index': i + 1,
                'description': step.description,
                'instruction': step.instruction,
                'action_type': step.action_type,
                'timestamp': step.timestamp,
                'x': step.x,
                'y': step.y,
                'width': step.width,
                'height': step.height,
                'shape': step.shape,
                'keyboard_mode': step.keyboard_mode,
                'keyboard_input': step.keyboard_input
            }
            steps_data.append(step_info)
        
        # Copy audio file if exists
        audio_basename = ""
        if self.tutorial.audio_path and os.path.exists(self.tutorial.audio_path):
            audio_basename = "tutorial_audio" + os.path.splitext(self.tutorial.audio_path)[1]
            audio_output = os.path.join(output_dir, audio_basename)
            shutil.copy2(self.tutorial.audio_path, audio_output)
            print(f"Copied audio to: {audio_output}")
        
        html_content = self._generate_video_html(steps_data, video_basename, audio_basename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Exported Video HTML to: {output_path}")
        return True
    
    def _generate_video_html(self, steps_data: list, video_file: str, audio_file: str = "") -> str:
        """Generate HTML with video player and interactive hitbox overlay."""
        steps_json = json.dumps(steps_data)
        
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.tutorial.title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            min-height: 100vh;
            color: white;
            overflow: hidden;
        }}
        
        .progress-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
            background: rgba(255,255,255,0.1);
            z-index: 1000;
        }}
        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5, #9333ea);
            transition: width 0.3s ease;
        }}
        
        .header {{
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.8);
            padding: 12px 30px;
            border-radius: 30px;
            backdrop-filter: blur(10px);
            z-index: 100;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        .step-badge {{
            background: linear-gradient(135deg, #ff6b6b, #ff8e53);
            width: 35px;
            height: 35px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
        }}
        .step-desc {{ font-size: 1.1em; }}
        .step-instruction {{
            font-size: 0.9em;
            color: #aaa;
            margin-top: 5px;
            max-width: 500px;
        }}
        
        .video-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            background: black;
        }}
        
        .video-wrapper {{
            position: relative;
            max-width: 100%;
            max-height: 100%;
        }}
        
        video {{
            max-width: 100vw;
            max-height: 100vh;
            display: block;
        }}
        
        .hitbox {{
            position: absolute;
            border: 3px solid #ff4444;
            cursor: pointer;
            display: none;
            animation: pulse 1.5s infinite, glow 1.5s infinite;
        }}
        .hitbox:hover {{
            border-color: #ffff00;
        }}
        .hitbox.circle {{
            border-radius: 50%;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); }}
            50% {{ transform: scale(1.03); }}
        }}
        
        @keyframes glow {{
            0%, 100% {{ 
                box-shadow: 0 0 10px rgba(255, 68, 68, 0.5), 
                            0 0 20px rgba(255, 68, 68, 0.3);
            }}
            50% {{ 
                box-shadow: 0 0 20px rgba(255, 68, 68, 0.8), 
                            0 0 40px rgba(255, 68, 68, 0.5);
            }}
        }}
        
        .modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: transparent;
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 500;
        }}
        .modal-overlay.active {{ display: flex; }}
        .modal-content {{
            background: linear-gradient(145deg, #1e1e2e, #2a2a3e);
            padding: 40px;
            border-radius: 20px;
            text-align: center;
        }}
        .modal-title {{ font-size: 1.5em; margin-bottom: 10px; color: #00d2ff; }}
        .modal-hint {{ color: #888; margin-bottom: 20px; }}
        .modal-input {{
            width: 300px;
            padding: 15px;
            font-size: 1.2em;
            border: 2px solid #444;
            border-radius: 10px;
            background: #1a1a2e;
            color: white;
            text-align: center;
            position: relative;
            z-index: 2;
        }}
        .modal-input-wrap {{
            position: relative;
            width: 300px;
            margin: 0 auto;
        }}
        .modal-input-ghost {{
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: rgba(255, 255, 255, 0.45);
            pointer-events: none;
            font-size: 1.2em;
            padding: 15px;
            z-index: 3;
        }}
        .modal-input:focus {{ border-color: #00d2ff; outline: none; }}
        .modal-input.success {{ border-color: #4CAF50; }}
        .modal-input.error {{ border-color: #ff4444; animation: shake 0.3s; }}
        
        @keyframes shake {{
            0%, 100% {{ transform: translateX(0); }}
            25% {{ transform: translateX(-10px); }}
            75% {{ transform: translateX(10px); }}
        }}
        
        .screen-overlay {{
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            transition: opacity 0.5s;
        }}
        .screen-overlay.hidden {{ opacity: 0; pointer-events: none; }}
        .screen-title {{
            font-size: 3em;
            margin-bottom: 20px;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .screen-subtitle {{ font-size: 1.3em; color: #888; margin-bottom: 40px; }}
        .screen-btn {{
            padding: 20px 60px;
            font-size: 1.3em;
            border: none;
            border-radius: 50px;
            background: linear-gradient(135deg, #00d2ff, #3a7bd5);
            color: white;
            cursor: pointer;
            transition: all 0.3s;
        }}
        .screen-btn:hover {{ transform: translateY(-3px); }}
        .completion-icon {{ font-size: 5em; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="progress-container">
        <div class="progress-bar" id="progressBar"></div>
    </div>
    
    <div class="header" id="header">
        <div class="step-badge" id="stepBadge">1</div>
        <div>
            <div class="step-desc" id="stepDesc">Loading...</div>
            <div class="step-instruction" id="stepInstruction"></div>
        </div>
    </div>
    
    <div class="video-container">
        <div class="video-wrapper" id="videoWrapper">
            <video id="video" src="{video_file}" preload="auto"></video>
            <div class="hitbox" id="hitbox"></div>
        </div>
    </div>
    
    <!-- Audio element for narration sync -->
    <audio id="audio" src="{audio_file}" preload="auto"></audio>
    
    <div class="modal-overlay" id="keyboardModal">
        <div class="modal-content">
            <div class="modal-title">⌨️ Type the required text</div>
            <div class="modal-hint" id="modalHint">Enter the text</div>
            <div class="modal-input-wrap" id="modalInputWrap">
                <input type="text" class="modal-input" id="modalInput" autocomplete="off">
                <div class="modal-input-ghost" id="modalInputGhost"></div>
            </div>
        </div>
    </div>
    
    <div class="screen-overlay" id="startScreen">
        <div class="screen-title">{self.tutorial.title}</div>
        <div class="screen-subtitle">Interactive Video Tutorial</div>
        <button class="screen-btn" id="startBtn" onclick="startTutorial()">▶ Start</button>
    </div>
    
    <div class="screen-overlay hidden" id="completionScreen">
        <div class="completion-icon">🎉</div>
        <div class="screen-title">Tutorial Complete!</div>
        <div class="screen-subtitle">Great job!</div>
        <button class="screen-btn" onclick="restartTutorial()">🔄 Restart</button>
    </div>
    
    <script>
        const steps = {steps_json};
        let currentStep = 0;
        let isPaused = false;
        
        const video = document.getElementById('video');
        const videoWrapper = document.getElementById('videoWrapper');
        const hitbox = document.getElementById('hitbox');
        const keyboardModal = document.getElementById('keyboardModal');
        const modalInput = document.getElementById('modalInput');
        const modalHint = document.getElementById('modalHint');
        const modalInputGhost = document.getElementById('modalInputGhost');
        const modalInputWrap = document.getElementById('modalInputWrap');
        const audio = document.getElementById('audio');
        const audioOffset = {self.tutorial.audio_offset};  // Audio sync offset in seconds
        
        function startTutorial() {{
            document.getElementById('startScreen').classList.add('hidden');
            document.getElementById('startBtn').textContent = '🔄 Restart';
            currentStep = 0;
            isPaused = false;
            video.currentTime = 0;
            video.play();
            
            // Start audio with offset
            if (audio.src) {{
                if (audioOffset >= 0) {{
                    setTimeout(() => {{ audio.currentTime = 0; audio.play(); }}, audioOffset * 1000);
                }} else {{
                    audio.currentTime = -audioOffset;
                    audio.play();
                }}
            }}
        }}
        
        function restartTutorial() {{
            document.getElementById('completionScreen').classList.add('hidden');
            startTutorial();
        }}
        
        video.addEventListener('timeupdate', function() {{
            if (isPaused || currentStep >= steps.length) return;
            
            const step = steps[currentStep];
            if (video.currentTime >= step.timestamp) {{
                pauseAndShowHitbox(step);
            }}
        }});
        
        function pauseAndShowHitbox(step) {{
            video.pause();
            if (audio.src) audio.pause();  // Pause audio in sync
            isPaused = true;
            
            document.getElementById('stepBadge').textContent = step.index;
            document.getElementById('stepDesc').textContent = step.description;
            document.getElementById('stepInstruction').textContent = step.instruction || '';
            document.getElementById('progressBar').style.width = ((currentStep + 1) / steps.length * 100) + '%';
            
            if (step.action_type === 'keyboard') {{
                hitbox.style.display = 'none';
                showKeyboardModal(step);
            }} else {{
                hideKeyboardModal();
                positionHitbox(step);
            }}
        }}
        
        function positionHitbox(step) {{
            const videoRect = video.getBoundingClientRect();
            const scaleX = videoRect.width / video.videoWidth;
            const scaleY = videoRect.height / video.videoHeight;
            
            hitbox.style.display = 'block';
            hitbox.style.left = (step.x * scaleX) + 'px';
            hitbox.style.top = (step.y * scaleY) + 'px';
            hitbox.style.width = (step.width * scaleX) + 'px';
            hitbox.style.height = (step.height * scaleY) + 'px';
            hitbox.className = 'hitbox' + (step.shape === 'circle' ? ' circle' : '');
            hitbox.style.background = 'rgba(255, 68, 68, 0.3)';
        }}
        
        hitbox.addEventListener('click', function() {{
            this.style.background = 'rgba(0, 255, 0, 0.5)';
            setTimeout(nextStep, 200);
        }});
        
        function nextStep() {{
            hitbox.style.display = 'none';
            currentStep++;
            isPaused = false;
            
            if (currentStep >= steps.length) {{
                if (audio.src) audio.pause();  // Stop audio on completion
                showCompletion();
            }} else {{
                video.play();
                if (audio.src) audio.play();  // Resume audio with video
            }}
        }}
        
        function showKeyboardModal(step) {{
            keyboardModal.classList.add('active');
            document.onkeydown = null;
            const customInstruction = (step.instruction || '').trim();
            
            let expectedInput = step.keyboard_input.toLowerCase().trim();
            if (expectedInput.startsWith('key.')) expectedInput = expectedInput.substring(4);
            
            const keyAliases = {{
                'escape': 'esc',
                'return': 'enter',
                'del': 'delete',
                'arrowup': 'up',
                'arrowdown': 'down',
                'arrowleft': 'left',
                'arrowright': 'right',
                'page_up': 'pageup',
                'page_down': 'pagedown'
            }};
            expectedInput = keyAliases[expectedInput] || expectedInput;
            
            const specialKeys = ['delete', 'backspace', 'tab', 'esc', 'enter',
                               'space', 'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown',
                               'insert', 'ctrl', 'alt', 'shift', 'cmd', 'capslock', 'numlock',
                               'scrolllock', 'pause', 'printscreen'];
            const isFkey = expectedInput.startsWith('f') && expectedInput.length >= 2 && !isNaN(expectedInput.substring(1));
            const inferredSpecial = specialKeys.includes(expectedInput) || isFkey;
            const isSpecial = (step.keyboard_mode || '') === 'key' || inferredSpecial;
            
            if (isSpecial) {{
                modalHint.textContent = customInstruction || `Press: ${{step.keyboard_input}}`;
                modalHint.style.display = 'block';
                modalInput.style.display = 'none';
                modalInputWrap.style.display = 'none';
                modalInputGhost.textContent = '';
            }} else {{
                modalHint.textContent = customInstruction || '';
                modalHint.style.display = customInstruction ? 'block' : 'none';
                modalInput.style.display = 'block';
                modalInputWrap.style.display = 'block';
                modalInputGhost.textContent = step.keyboard_input;
                modalInput.focus();
            }}
            
            modalInput.value = '';
            modalInput.className = 'modal-input';
            
            document.onkeydown = function(e) {{
                let keyName = e.key.toLowerCase();
                if (e.key === 'Delete') keyName = 'delete';
                else if (e.key === 'Backspace') keyName = 'backspace';
                else if (e.key === 'Tab') keyName = 'tab';
                else if (e.key === 'Escape') keyName = 'esc';
                else if (e.key === 'Enter') keyName = 'enter';
                else if (e.key === ' ') keyName = 'space';
                else if (e.key === 'ArrowUp') keyName = 'up';
                else if (e.key === 'ArrowDown') keyName = 'down';
                else if (e.key === 'ArrowLeft') keyName = 'left';
                else if (e.key === 'ArrowRight') keyName = 'right';
                else if (e.key === 'Home') keyName = 'home';
                else if (e.key === 'End') keyName = 'end';
                else if (e.key === 'PageUp') keyName = 'pageup';
                else if (e.key === 'PageDown') keyName = 'pagedown';
                else if (e.key === 'Insert') keyName = 'insert';
                else if (e.key.startsWith('F') && e.key.length > 1) keyName = e.key.toLowerCase();
                
                if (isSpecial && keyName === expectedInput) {{
                    e.preventDefault();
                    modalInput.className = 'modal-input success';
                    document.onkeydown = null;
                    setTimeout(function() {{ hideKeyboardModal(); nextStep(); }}, 200);
                    return false;
                }}
                
                // For text input, check on Enter or Space
                if (!isSpecial && (keyName === 'enter' || keyName === 'space')) {{
                    if (modalInput.value.toLowerCase() === expectedInput) {{
                        modalInput.className = 'modal-input success';
                        document.onkeydown = null;
                        setTimeout(function() {{ hideKeyboardModal(); nextStep(); }}, 300);
                    }} else {{
                        modalInput.className = 'modal-input error';
                        setTimeout(function() {{ modalInput.className = 'modal-input'; }}, 300);
                    }}
                }}
            }};
        }}
        
        function hideKeyboardModal() {{
            document.onkeydown = null;
            keyboardModal.classList.remove('active');
        }}

        modalInput.addEventListener('input', function() {{
            modalInputGhost.style.display = modalInput.value ? 'none' : 'flex';
        }});
        
        function showCompletion() {{
            document.getElementById('completionScreen').classList.remove('hidden');
            document.getElementById('progressBar').style.width = '100%';
        }}
        
        video.addEventListener('ended', function() {{
            if (currentStep >= steps.length) {{
                showCompletion();
            }}
        }});
    </script>
</body>
</html>'''
