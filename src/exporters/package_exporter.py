"""
Package Exporter Module
Exports tutorials to SCORM package and standalone EXE formats
"""
import os
import json
import shutil
import zipfile
import uuid
from typing import Callable, Optional
from ..model import Tutorial


class PackageExporter:
    """Export tutorial to packaged formats."""
    
    def __init__(self, tutorial: Tutorial, progress_callback: Optional[Callable[[int], None]] = None):
        self.tutorial = tutorial
        self.progress_callback = progress_callback

    def _get_temp_parent_dir(self, output_path: str) -> str:
        output_dir = os.path.dirname(output_path)
        if output_dir and os.path.exists(output_dir):
            return output_dir
        return os.getcwd()

    def _make_work_dir(self, output_path: str, prefix: str) -> str:
        parent_dir = self._get_temp_parent_dir(output_path)
        work_dir = os.path.join(parent_dir, f"{prefix}_{uuid.uuid4().hex[:8]}")
        os.makedirs(work_dir, exist_ok=False)
        return work_dir
    
    def export_scorm(self, output_path: str) -> bool:
        """Export as SCORM 1.2 package for LMS integration."""
        from .web_exporter import WebExporter
        
        temp_dir = self._make_work_dir(output_path, "_scorm_build")
        try:
            # Export HTML content
            web_exporter = WebExporter(self.tutorial)
            html_path = os.path.join(temp_dir, 'index.html')
            web_exporter.export_html(html_path, embed_images=True)
            
            if self.progress_callback:
                self.progress_callback(30)
            
            # Create imsmanifest.xml (SCORM 1.2)
            manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="com.tutomake.{self.tutorial.title.replace(' ', '_')}" version="1.0"
    xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
    xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
    
    <metadata>
        <schema>ADL SCORM</schema>
        <schemaversion>1.2</schemaversion>
    </metadata>
    
    <organizations default="tutomake_org">
        <organization identifier="tutomake_org">
            <title>{self.tutorial.title}</title>
            <item identifier="item_1" identifierref="resource_1">
                <title>{self.tutorial.title}</title>
            </item>
        </organization>
    </organizations>
    
    <resources>
        <resource identifier="resource_1" type="webcontent" adlcp:scormtype="sco" href="index.html">
            <file href="index.html"/>
            <file href="scorm_api.js"/>
        </resource>
    </resources>
</manifest>'''
            
            manifest_path = os.path.join(temp_dir, 'imsmanifest.xml')
            with open(manifest_path, 'w', encoding='utf-8') as f:
                f.write(manifest)
            
            if self.progress_callback:
                self.progress_callback(50)
            
            # Create SCORM API wrapper
            scorm_js = '''// SCORM 1.2 API Wrapper
var API = null;

function findAPI(win) {
    var tries = 0;
    while (win.API == null && win.parent != null && win.parent != win && tries < 10) {
        tries++;
        win = win.parent;
    }
    return win.API;
}

function initSCORM() {
    API = findAPI(window);
    if (API) {
        API.LMSInitialize("");
        API.LMSSetValue("cmi.core.lesson_status", "incomplete");
    }
}

function completeSCORM() {
    if (API) {
        API.LMSSetValue("cmi.core.lesson_status", "completed");
        API.LMSCommit("");
        API.LMSFinish("");
    }
}

window.onload = initSCORM;
window.onbeforeunload = function() {
    if (API) API.LMSFinish("");
};
'''
            scorm_js_path = os.path.join(temp_dir, 'scorm_api.js')
            with open(scorm_js_path, 'w', encoding='utf-8') as f:
                f.write(scorm_js)
            
            if self.progress_callback:
                self.progress_callback(70)
            
            # Create ZIP package
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zf.write(file_path, arcname)
            
            if self.progress_callback:
                self.progress_callback(100)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        print(f"Exported SCORM package to: {output_path}")
        return True
    
    def export_exe(self, output_path: str) -> bool:
        """
        Export as standalone Windows EXE.
        Note: This creates a batch script that launches the tutorial with Python.
        For true standalone EXE, use PyInstaller separately.
        """
        import tempfile
        from .web_exporter import WebExporter
        
        # Create output directory
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Export HTML first
        html_path = output_path.replace('.exe', '.html')
        web_exporter = WebExporter(self.tutorial)
        web_exporter.export_html(html_path, embed_images=True)
        
        if self.progress_callback:
            self.progress_callback(50)
        
        # Create launcher batch file (simple approach)
        bat_path = output_path.replace('.exe', '_launcher.bat')
        bat_content = f'''@echo off
start "" "{os.path.basename(html_path)}"
'''
        with open(bat_path, 'w') as f:
            f.write(bat_content)
        
        # Create instructions for true EXE
        readme_path = output_path.replace('.exe', '_README.txt')
        readme_content = f'''TutoMake Tutorial Export
========================

Files included:
- {os.path.basename(html_path)} - The tutorial (open in browser)
- {os.path.basename(bat_path)} - Launcher script

To create a true standalone EXE:
1. Install PyInstaller: pip install pyinstaller
2. Create a simple Python script that opens the HTML
3. Run: pyinstaller --onefile --windowed your_script.py

For now, double-click the .bat file or open the .html directly.
'''
        with open(readme_path, 'w') as f:
            f.write(readme_content)
        
        if self.progress_callback:
            self.progress_callback(100)
        
        print(f"Exported launcher to: {bat_path}")
        print("Note: For true EXE, use PyInstaller separately")
        return True
    
    def create_portable_package(self, output_path: str) -> bool:
        """Create a portable ZIP package with all files."""
        from .web_exporter import WebExporter
        from .document_exporter import DocumentExporter
        
        temp_dir = self._make_work_dir(output_path, "_portable_build")
        try:
            # Export HTML
            web_exporter = WebExporter(self.tutorial)
            web_exporter.export_html(os.path.join(temp_dir, 'tutorial.html'))
            
            if self.progress_callback:
                self.progress_callback(30)
            
            # Export Markdown
            doc_exporter = DocumentExporter(self.tutorial)
            doc_exporter.export_markdown(os.path.join(temp_dir, 'tutorial.md'))
            
            if self.progress_callback:
                self.progress_callback(50)
            
            # Export PNG sequence
            png_dir = os.path.join(temp_dir, 'images')
            doc_exporter.export_png_sequence(png_dir)
            
            if self.progress_callback:
                self.progress_callback(70)
            
            # Save JSON data
            json_path = os.path.join(temp_dir, 'tutorial.json')
            self.tutorial.save(json_path)
            
            # Create README
            readme = f'''# {self.tutorial.title}

## Contents
- tutorial.html - Interactive web tutorial
- tutorial.md - Markdown documentation
- tutorial.json - Raw tutorial data
- images/ - Step screenshots

## Usage
Open tutorial.html in any web browser to view the interactive tutorial.
'''
            with open(os.path.join(temp_dir, 'README.md'), 'w') as f:
                f.write(readme)
            
            if self.progress_callback:
                self.progress_callback(90)
            
            # Create ZIP
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zf.write(file_path, arcname)
            
            if self.progress_callback:
                self.progress_callback(100)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        print(f"Exported portable package to: {output_path}")
        return True
