#!/usr/bin/env python3
"""
Dependency Analyzer
===================
Analyseert welke modules door welke bestanden worden geïmporteerd.
"""

import ast
import os
from pathlib import Path
from collections import defaultdict
import json

class DependencyAnalyzer:
    def __init__(self, root_path="."):
        self.root = Path(root_path)
        self.imports = defaultdict(set)  # file -> set of imports
        self.imported_by = defaultdict(set)  # module -> set of files that import it
        self.definitions = defaultdict(set)  # file -> set of defined functions/classes
        self.local_modules = set()  # Python files in this project
        
    def find_local_modules(self):
        """Find all local Python modules."""
        for py_file in self.root.rglob("*.py"):
            if '__pycache__' in str(py_file):
                continue
            # Convert path to module name
            rel_path = py_file.relative_to(self.root)
            module_name = str(rel_path).replace('/', '.').replace('\\', '.').replace('.py', '')
            if module_name.endswith('.__init__'):
                module_name = module_name[:-9]
            self.local_modules.add(module_name)
            # Also add just the filename without extension
            self.local_modules.add(py_file.stem)
        
        print(f"Found {len(self.local_modules)} local modules")
        
    def analyze_file(self, filepath):
        """Analyze a single Python file."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            tree = ast.parse(content)
            rel_path = str(Path(filepath).relative_to(self.root))
            
            file_imports = set()
            file_definitions = set()
            
            for node in ast.walk(tree):
                # Collect imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name.split('.')[0]
                        file_imports.add(module)
                        
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module = node.module.split('.')[0]
                        file_imports.add(module)
                    for alias in node.names:
                        if alias.name != '*':
                            file_imports.add(alias.name)
                
                # Collect definitions
                elif isinstance(node, ast.FunctionDef):
                    file_definitions.add(f"def {node.name}")
                elif isinstance(node, ast.AsyncFunctionDef):
                    file_definitions.add(f"async def {node.name}")
                elif isinstance(node, ast.ClassDef):
                    file_definitions.add(f"class {node.name}")
            
            self.imports[rel_path] = file_imports
            self.definitions[rel_path] = file_definitions
            
            # Track what imports what (only for local modules)
            for imp in file_imports:
                if imp in self.local_modules or any(imp in m for m in self.local_modules):
                    self.imported_by[imp].add(rel_path)
            
            return {
                'path': rel_path,
                'imports': list(file_imports),
                'definitions': list(file_definitions),
                'lines': len(content.splitlines()),
            }
            
        except SyntaxError as e:
            return {'path': str(filepath), 'error': f"Syntax error: {e}"}
        except Exception as e:
            return {'path': str(filepath), 'error': str(e)}
    
    def analyze_all(self):
        """Analyze all Python files."""
        self.find_local_modules()
        
        results = []
        for py_file in sorted(self.root.rglob("*.py")):
            if '__pycache__' in str(py_file):
                continue
            result = self.analyze_file(py_file)
            results.append(result)
        
        return results
    
    def find_unused_files(self):
        """Find files that are not imported by any other file."""
        all_files = set(self.imports.keys())
        
        # Known entry points that won't be imported
        known_entry_points = {
            'main_live_bot.py',
            'ftmo_challenge_analyzer.py',
            'run_optimization.sh',
            'setup.py',
            'test_v6_scoring.py',
        }
        
        unused = []
        for filepath in all_files:
            filename = Path(filepath).name
            stem = Path(filepath).stem
            
            # Skip known entry points
            if filename in known_entry_points:
                continue
            
            # Skip test files
            if 'test' in filename.lower():
                continue
            
            # Skip __init__.py
            if filename == '__init__.py':
                continue
            
            # Check if this file's module is imported anywhere
            is_imported = False
            for module, importers in self.imported_by.items():
                if stem == module or stem in module:
                    is_imported = True
                    break
            
            if not is_imported:
                unused.append(filepath)
        
        return unused
    
    def find_duplicate_definitions(self):
        """Find functions/classes defined in multiple files."""
        all_defs = defaultdict(list)
        
        for filepath, defs in self.definitions.items():
            for d in defs:
                all_defs[d].append(filepath)
        
        return {k: v for k, v in all_defs.items() if len(v) > 1}
    
    def generate_report(self):
        """Generate full analysis report."""
        results = self.analyze_all()
        unused = self.find_unused_files()
        duplicates = self.find_duplicate_definitions()
        
        report = []
        report.append("=" * 70)
        report.append("DEPENDENCY ANALYSIS REPORT")
        report.append("=" * 70)
        report.append("")
        
        # Summary
        total_lines = sum(r.get('lines', 0) for r in results if 'lines' in r)
        report.append(f"📊 SUMMARY")
        report.append(f"   Total Python files: {len(results)}")
        report.append(f"   Total lines of code: {total_lines:,}")
        report.append(f"   Potentially unused files: {len(unused)}")
        report.append(f"   Duplicate definitions: {len(duplicates)}")
        report.append("")
        
        # Files by location
        report.append("=" * 70)
        report.append("📁 FILES BY LOCATION")
        report.append("=" * 70)
        
        by_folder = defaultdict(list)
        for r in results:
            if 'error' in r:
                continue
            folder = str(Path(r['path']).parent)
            by_folder[folder].append(r)
        
        for folder in sorted(by_folder.keys()):
            report.append(f"\n📂 {folder}/")
            for r in sorted(by_folder[folder], key=lambda x: x['path']):
                filename = Path(r['path']).name
                lines = r.get('lines', 0)
                defs = len(r.get('definitions', []))
                report.append(f"   {filename:<35} {lines:>5} lines  {defs:>3} definitions")
        
        # Import graph for root files
        report.append("")
        report.append("=" * 70)
        report.append("📈 IMPORT GRAPH (root files)")
        report.append("=" * 70)
        
        for filepath, imports in sorted(self.imports.items()):
            if '/' in filepath:
                continue  # Skip subdirectories for now
            local_imports = [i for i in imports if i in self.local_modules]
            if local_imports:
                report.append(f"\n{filepath}:")
                for imp in sorted(local_imports):
                    report.append(f"   └── {imp}")
        
        # Unused files
        report.append("")
        report.append("=" * 70)
        report.append("⚠️ POTENTIALLY UNUSED FILES")
        report.append("=" * 70)
        report.append("These files are not imported by any other Python file.")
        report.append("⚠️ CAUTION: Entry points and scripts appear here but ARE used!")
        report.append("")
        
        for f in sorted(unused):
            report.append(f"   ❓ {f}")
        
        # Duplicate definitions
        if duplicates:
            report.append("")
            report.append("=" * 70)
            report.append("🔄 DUPLICATE DEFINITIONS")
            report.append("=" * 70)
            report.append("Same function/class defined in multiple files:")
            report.append("")
            
            for name, files in sorted(duplicates.items()):
                report.append(f"   {name}:")
                for f in files:
                    report.append(f"      - {f}")
        
        # Most imported modules
        report.append("")
        report.append("=" * 70)
        report.append("📦 MOST IMPORTED LOCAL MODULES")
        report.append("=" * 70)
        
        import_counts = [(mod, len(files)) for mod, files in self.imported_by.items()]
        import_counts.sort(key=lambda x: x[1], reverse=True)
        
        for mod, count in import_counts[:15]:
            report.append(f"   {mod:<30} imported by {count} file(s)")
        
        return "\n".join(report)


def main():
    analyzer = DependencyAnalyzer(".")
    report = analyzer.generate_report()
    
    print(report)
    
    # Save report
    with open("analysis/dependency_report.txt", "w") as f:
        f.write(report)
    
    # Save detailed JSON for further analysis
    results = analyzer.analyze_all()
    with open("analysis/dependency_data.json", "w") as f:
        json.dump({
            'files': results,
            'imports': {k: list(v) for k, v in analyzer.imports.items()},
            'imported_by': {k: list(v) for k, v in analyzer.imported_by.items()},
            'definitions': {k: list(v) for k, v in analyzer.definitions.items()},
        }, f, indent=2)
    
    print("\n" + "=" * 70)
    print("✅ Reports saved to:")
    print("   - analysis/dependency_report.txt")
    print("   - analysis/dependency_data.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
