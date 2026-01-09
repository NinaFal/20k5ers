#!/usr/bin/env python3
"""
Dead Code Detector
==================
Vindt functies en classes die nergens worden aangeroepen.
"""

import ast
import os
from pathlib import Path
from collections import defaultdict

class DeadCodeDetector:
    def __init__(self, root_path="."):
        self.root = Path(root_path)
        self.definitions = {}  # name -> (file, line, kind)
        self.usages = defaultdict(set)  # name -> set of files using it
        
    def analyze_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            tree = ast.parse(content)
        except:
            return
        
        rel_path = str(filepath.relative_to(self.root))
        
        # Find definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith('_'):  # Skip private
                    self.definitions[node.name] = (rel_path, node.lineno, 'function')
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith('_'):
                    self.definitions[node.name] = (rel_path, node.lineno, 'class')
        
        # Find usages
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                self.usages[node.id].add(rel_path)
            elif isinstance(node, ast.Attribute):
                self.usages[node.attr].add(rel_path)
    
    def find_dead_code(self):
        # Analyze all files
        for py_file in self.root.rglob("*.py"):
            if '__pycache__' in str(py_file):
                continue
            self.analyze_file(py_file)
        
        # Find unused
        dead = []
        for name, (filepath, line, kind) in self.definitions.items():
            usages = self.usages.get(name, set())
            
            # Remove self-usage
            other_usages = usages - {filepath}
            
            # If only used in defining file or not used at all
            if len(other_usages) == 0:
                dead.append({
                    'name': name,
                    'kind': kind,
                    'file': filepath,
                    'line': line,
                    'self_usage': filepath in usages,
                })
        
        return dead
    
    def generate_report(self):
        dead = self.find_dead_code()
        
        report = []
        report.append("=" * 70)
        report.append("DEAD CODE ANALYSIS")
        report.append("=" * 70)
        report.append(f"\nFound {len(dead)} potentially unused definitions\n")
        report.append("⚠️ CAUTION: These may be used via:")
        report.append("   - Dynamic imports")
        report.append("   - String-based lookups")
        report.append("   - External tools/scripts")
        report.append("   - Test files")
        report.append("\nVERIFY before removing!\n")
        
        # Group by file
        by_file = defaultdict(list)
        for item in dead:
            by_file[item['file']].append(item)
        
        for filepath in sorted(by_file.keys()):
            items = by_file[filepath]
            report.append(f"\n📄 {filepath}")
            for item in sorted(items, key=lambda x: x['line']):
                marker = "📍" if item['self_usage'] else "❌"
                report.append(f"   {marker} Line {item['line']:>4}: {item['kind']} {item['name']}")
        
        return "\n".join(report)


def main():
    detector = DeadCodeDetector(".")
    report = detector.generate_report()
    
    print(report)
    
    with open("analysis/dead_code_report.txt", "w") as f:
        f.write(report)
    
    print("\n✅ Report saved to: analysis/dead_code_report.txt")


if __name__ == "__main__":
    main()
