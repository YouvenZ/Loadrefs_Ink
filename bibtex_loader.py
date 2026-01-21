
# MIT License

# Copyright (c) 2026 Rachid, Youven ZEGHLACHE
#!/usr/bin/env python3


#!/usr/bin/env python3
"""
Inkscape extension to load reference files and add formatted references to drawings.
Supports BibTeX, RIS, and JSON formats.
Supports both Inkscape native text and LaTeX rendering.
"""

import inkex
from inkex import TextElement, Rectangle, Group, Transform, Tspan
import re
from pathlib import Path
import json
import tempfile
import subprocess
import shutil
import os
from lxml import etree


class BibTeXLoader(inkex.EffectExtension):
    """Extension to load and display references in Inkscape."""
    
    def add_arguments(self, pars):
        pars.add_argument("--tab", type=str, default="file", help="Active tab")
        pars.add_argument("--bibfile", type=str, default="", help="Path to reference file")
        pars.add_argument("--backend", type=str, default="inkscape", help="Backend: inkscape or latex")
        pars.add_argument("--format", type=str, default="apa", help="Citation format")
        pars.add_argument("--font_size", type=int, default=11, help="Font size")
        pars.add_argument("--line_spacing", type=float, default=1.3, help="Line spacing")
        pars.add_argument("--max_width", type=int, default=600, help="Maximum width")
        pars.add_argument("--add_box", type=inkex.Boolean, default=True, help="Add background box")
        pars.add_argument("--box_padding", type=int, default=15, help="Box padding")
        pars.add_argument("--font_family", type=str, default="serif", help="Font family")
        pars.add_argument("--numbering_style", type=str, default="numeric", help="Numbering style")
        pars.add_argument("--sort_order", type=str, default="appearance", help="Sort order")
        pars.add_argument("--hanging_indent", type=inkex.Boolean, default=True, help="Use hanging indent")
        pars.add_argument("--indent_size", type=int, default=20, help="Indent size in pixels")
        pars.add_argument("--title_text", type=str, default="References", help="Title text")
        pars.add_argument("--show_title", type=inkex.Boolean, default=True, help="Show title")
        pars.add_argument("--update_existing", type=inkex.Boolean, default=False, help="Update existing references")
        
        # Position arguments
        pars.add_argument("--x_position", type=int, default=100, help="X position on canvas")
        pars.add_argument("--y_position", type=int, default=100, help="Y position on canvas")
        pars.add_argument("--position_mode", type=str, default="custom", help="Position mode: custom, center, top-left, etc.")
        
        # LaTeX options
        pars.add_argument("--latex_preamble", type=str, default="", help="LaTeX preamble")
        pars.add_argument("--latex_packages", type=str, default="", help="Additional LaTeX packages")
    
    def effect(self):
        """Main effect function."""
        # Check if we should update existing references
        if self.options.update_existing:
            existing_group = self.find_existing_references()
            if existing_group:
                # Remove the existing group
                existing_group.getparent().remove(existing_group)
        
        bibfile = self.options.bibfile
        
        if not bibfile or not Path(bibfile).exists():
            inkex.errormsg(f"Please provide a valid reference file path.\nReceived: {bibfile}")
            return
        
        # Parse reference file based on extension
        file_path = Path(bibfile)
        entries = self.parse_reference_file(file_path)
        
        if not entries:
            inkex.errormsg("No valid reference entries found in the file.")
            return
        
        # Sort entries
        entries = self.sort_entries(entries)
        
        # Format references
        formatted_refs = self.format_with_python(entries)
        
        # Choose backend
        if self.options.backend == "latex":
            try:
                self.add_references_latex(formatted_refs, entries)
            except Exception as e:
                inkex.errormsg(f"LaTeX rendering failed: {str(e)}")
                inkex.utils.debug("Falling back to Inkscape backend")
                self.add_references_to_document(formatted_refs)
        else:
            self.add_references_to_document(formatted_refs)
    
    def get_position(self):
        """Calculate position based on position mode."""
        svg_width = self.svg.viewport_width
        svg_height = self.svg.viewport_height
        
        mode = self.options.position_mode
        
        if mode == "center":
            return (svg_width / 2, svg_height / 2)
        elif mode == "top-left":
            return (50, 50)
        elif mode == "top-center":
            return (svg_width / 2, 50)
        elif mode == "top-right":
            return (svg_width - 50, 50)
        elif mode == "bottom-left":
            return (50, svg_height - 50)
        elif mode == "bottom-center":
            return (svg_width / 2, svg_height - 50)
        elif mode == "bottom-right":
            return (svg_width - 50, svg_height - 50)
        else:  # custom
            return (self.options.x_position, self.options.y_position)
    
    def find_existing_references(self):
        """Find existing references group in the document."""
        # Look for groups with id starting with 'references'
        for elem in self.svg.xpath('//svg:g[@id]'):
            elem_id = elem.get('id', '')
            if elem_id.startswith('references'):
                return elem
        return None
    
    def parse_reference_file(self, filepath):
        """Parse reference file based on extension."""
        extension = filepath.suffix.lower()
        
        if extension == '.bib':
            return self.parse_bibtex(filepath)
        elif extension == '.ris':
            return self.parse_ris(filepath)
        elif extension == '.json':
            return self.parse_json(filepath)
        elif extension in ['.enw', '.endnote']:
            return self.parse_endnote(filepath)
        else:
            inkex.errormsg(f"Unsupported file format: {extension}")
            return []
    
    def parse_bibtex(self, filepath):
        """Parse a BibTeX file and extract entries."""
        entries = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Regex to match BibTeX entries
            pattern = r'@(\w+)\s*\{\s*([^,]+)\s*,\s*((?:[^{}]|\{[^{}]*\})*)\}'
            matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)
            
            for match in matches:
                entry_type = match.group(1)
                cite_key = match.group(2).strip()
                fields_str = match.group(3)
                
                # Parse fields
                fields = {}
                field_pattern = r'(\w+)\s*=\s*[{"]((?:[^{}"]|\{[^{}]*\})*)[}"]'
                for field_match in re.finditer(field_pattern, fields_str, re.DOTALL):
                    field_name = field_match.group(1).lower()
                    field_value = field_match.group(2).strip()
                    # Remove extra braces
                    field_value = re.sub(r'\{([^{}]*)\}', r'\1', field_value)
                    fields[field_name] = field_value
                
                entries.append({
                    'type': entry_type.lower(),
                    'key': cite_key,
                    'fields': fields
                })
        
        except Exception as e:
            inkex.errormsg(f"Error parsing BibTeX file: {str(e)}")
            return []
        
        return entries
    
    def parse_ris(self, filepath):
        """Parse RIS format file."""
        entries = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split by record separator
            records = content.split('ER  -')
            
            for record in records:
                if not record.strip():
                    continue
                
                fields = {}
                entry_type = 'article'
                
                # Parse RIS tags
                for line in record.split('\n'):
                    line = line.strip()
                    if not line or '  -' not in line:
                        continue
                    
                    tag, value = line.split('  -', 1)
                    tag = tag.strip()
                    value = value.strip()
                    
                    if tag == 'TY':
                        entry_type = value.lower()
                    elif tag == 'AU':
                        if 'author' in fields:
                            fields['author'] += ' and ' + value
                        else:
                            fields['author'] = value
                    elif tag == 'TI':
                        fields['title'] = value
                    elif tag == 'PY':
                        fields['year'] = value.split('/')[0]  # Extract year
                    elif tag == 'JO' or tag == 'JF' or tag == 'T2':
                        fields['journal'] = value
                    elif tag == 'VL':
                        fields['volume'] = value
                    elif tag == 'IS':
                        fields['number'] = value
                    elif tag == 'SP':
                        fields['pages'] = value
                    elif tag == 'EP' and 'pages' in fields:
                        fields['pages'] += '-' + value
                    elif tag == 'PB':
                        fields['publisher'] = value
                
                if fields:
                    entries.append({
                        'type': entry_type,
                        'key': fields.get('title', 'unknown')[:20],
                        'fields': fields
                    })
        
        except Exception as e:
            inkex.errormsg(f"Error parsing RIS file: {str(e)}")
            return []
        
        return entries
    
    def parse_json(self, filepath):
        """Parse JSON format file (CSL JSON)."""
        entries = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle both array and object formats
            if isinstance(data, dict):
                data = [data]
            
            for item in data:
                fields = {}
                
                # Extract authors
                if 'author' in item:
                    authors = []
                    for author in item['author']:
                        if isinstance(author, dict):
                            if 'family' in author and 'given' in author:
                                authors.append(f"{author['given']} {author['family']}")
                            elif 'literal' in author:
                                authors.append(author['literal'])
                    fields['author'] = ' and '.join(authors)
                
                # Map common fields
                field_map = {
                    'title': 'title',
                    'container-title': 'journal',
                    'publisher': 'publisher',
                    'volume': 'volume',
                    'issue': 'number',
                    'page': 'pages'
                }
                
                for json_field, bib_field in field_map.items():
                    if json_field in item:
                        fields[bib_field] = str(item[json_field])
                
                # Extract year
                if 'issued' in item:
                    if isinstance(item['issued'], dict) and 'date-parts' in item['issued']:
                        fields['year'] = str(item['issued']['date-parts'][0][0])
                    elif isinstance(item['issued'], str):
                        fields['year'] = item['issued'][:4]
                
                entry_type = item.get('type', 'article-journal')
                if 'journal' in entry_type:
                    entry_type = 'article'
                
                entries.append({
                    'type': entry_type,
                    'key': item.get('id', fields.get('title', 'unknown')[:20]),
                    'fields': fields
                })
        
        except Exception as e:
            inkex.errormsg(f"Error parsing JSON file: {str(e)}")
            return []
        
        return entries
    
    def parse_endnote(self, filepath):
        """Parse EndNote format file."""
        entries = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split by record separator
            records = re.split(r'\n\s*\n', content)
            
            for record in records:
                if not record.strip():
                    continue
                
                fields = {}
                entry_type = 'article'
                
                # Parse EndNote tags
                for line in record.split('\n'):
                    if not line.strip() or not line.startswith('%'):
                        continue
                    
                    tag = line[1]
                    value = line[2:].strip()
                    
                    if tag == '0':
                        entry_type = value.lower()
                    elif tag == 'A':
                        if 'author' in fields:
                            fields['author'] += ' and ' + value
                        else:
                            fields['author'] = value
                    elif tag == 'T':
                        fields['title'] = value
                    elif tag == 'D':
                        fields['year'] = value[:4]
                    elif tag == 'J':
                        fields['journal'] = value
                    elif tag == 'V':
                        fields['volume'] = value
                    elif tag == 'N':
                        fields['number'] = value
                    elif tag == 'P':
                        fields['pages'] = value
                    elif tag == 'I':
                        fields['publisher'] = value
                
                if fields:
                    entries.append({
                        'type': entry_type,
                        'key': fields.get('title', 'unknown')[:20],
                        'fields': fields
                    })
        
        except Exception as e:
            inkex.errormsg(f"Error parsing EndNote file: {str(e)}")
            return []
        
        return entries
    
    def sort_entries(self, entries):
        """Sort entries based on selected order."""
        if self.options.sort_order == 'author':
            return sorted(entries, key=lambda x: x['fields'].get('author', '').lower())
        elif self.options.sort_order == 'year':
            return sorted(entries, key=lambda x: x['fields'].get('year', '9999'))
        elif self.options.sort_order == 'title':
            return sorted(entries, key=lambda x: x['fields'].get('title', '').lower())
        else:  # appearance
            return entries
    
    def format_with_python(self, entries):
        """Format references using Python."""
        refs = []
        format_style = self.options.format
        
        for entry in entries:
            formatted = self.format_entry_python(entry, format_style)
            if formatted:
                refs.append(formatted)
        
        return refs
    
    def get_numbering_marker(self, index):
        """Get the numbering marker based on style."""
        style = self.options.numbering_style
        
        if style == 'numeric':
            return f"[{index}]"
        elif style == 'numeric_dot':
            return f"{index}."
        elif style == 'numeric_paren':
            return f"({index})"
        elif style == 'bullet':
            return "•"
        elif style == 'dash':
            return "–"
        elif style == 'asterisk':
            return "*"
        elif style == 'symbols':
            symbols = ['*', '†', '‡', '§', '¶', '‖', '**', '††', '‡‡']
            if index - 1 < len(symbols):
                return symbols[index - 1]
            else:
                return f"[{index}]"
        elif style == 'alpha':
            if index <= 26:
                return f"{chr(96 + index)}."
            else:
                return f"[{index}]"
        elif style == 'roman':
            roman_numerals = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x',
                            'xi', 'xii', 'xiii', 'xiv', 'xv', 'xvi', 'xvii', 'xviii', 'xix', 'xx']
            if index - 1 < len(roman_numerals):
                return f"{roman_numerals[index - 1]}."
            else:
                return f"[{index}]"
        elif style == 'none':
            return ""
        else:
            return f"[{index}]"
    
    def format_entry_python(self, entry, style):
        """Format a single entry according to the specified style."""
        fields = entry['fields']
        entry_type = entry['type']
        
        # Common field extractions
        authors = self.format_authors(fields.get('author', ''), style)
        year = fields.get('year', 'n.d.')
        title = fields.get('title', '')
        
        # Style-specific formatting
        if style == 'apa' or style == 'apa7':
            return self.format_apa(entry_type, authors, year, title, fields)
        elif style == 'mla':
            return self.format_mla(entry_type, authors, year, title, fields)
        elif style == 'chicago':
            return self.format_chicago(entry_type, authors, year, title, fields)
        elif style == 'harvard':
            return self.format_harvard(entry_type, authors, year, title, fields)
        elif style == 'ieee':
            return self.format_ieee(entry_type, authors, year, title, fields)
        elif style == 'vancouver':
            return self.format_vancouver(entry_type, authors, year, title, fields)
        elif style == 'ama':
            return self.format_ama(entry_type, authors, year, title, fields)
        elif style == 'acs':
            return self.format_acs(entry_type, authors, year, title, fields)
        elif style == 'nature':
            return self.format_nature(entry_type, authors, year, title, fields)
        else:
            return self.format_apa(entry_type, authors, year, title, fields)
    
    def format_authors(self, author_str, style):
        """Format author names according to style."""
        if not author_str:
            return ''
        
        authors = [a.strip() for a in author_str.replace(' and ', ', ').split(',')]
        authors = [a for a in authors if a]
        
        if style in ['apa', 'apa7', 'chicago', 'harvard']:
            # Last, F. M. format
            formatted = []
            for author in authors:
                parts = author.split()
                if len(parts) > 1:
                    last = parts[-1]
                    initials = '. '.join([p[0] for p in parts[:-1] if p]) + '.'
                    formatted.append(f"{last}, {initials}")
                else:
                    formatted.append(author)
            
            if len(formatted) > 2:
                return ', '.join(formatted[:-1]) + ', & ' + formatted[-1]
            elif len(formatted) == 2:
                return f"{formatted[0]} & {formatted[1]}"
            else:
                return formatted[0] if formatted else ''
        
        elif style == 'mla':
            # Last, First Middle format
            if len(authors) > 1:
                return authors[0] + ', et al.'
            return authors[0]
        
        elif style in ['ieee', 'vancouver', 'nature']:
            # Abbreviated format
            formatted = []
            for author in authors[:6]:  # Limit to 6 authors
                parts = author.split()
                if len(parts) > 1:
                    initials = ''.join([p[0] for p in parts[:-1] if p])
                    formatted.append(f"{parts[-1]} {initials}")
                else:
                    formatted.append(author)
            
            if len(authors) > 6:
                return ', '.join(formatted) + ', et al.'
            return ', '.join(formatted)
        
        else:
            return ', '.join(authors)
    
    def format_apa(self, entry_type, authors, year, title, fields):
        """APA format."""
        parts = []
        
        if authors:
            parts.append(f"{authors} ({year}).")
        else:
            parts.append(f"({year}).")
        
        if entry_type == 'article':
            parts.append(f"{title}.")
            if 'journal' in fields:
                journal = fields['journal']
                vol_str = f"{journal}"
                if 'volume' in fields:
                    vol_str += f", {fields['volume']}"
                if 'number' in fields:
                    vol_str += f"({fields['number']})"
                if 'pages' in fields:
                    vol_str += f", {fields['pages']}"
                parts.append(vol_str + ".")
        else:
            parts.append(f"{title}.")
            if 'publisher' in fields:
                parts.append(f"{fields['publisher']}.")
        
        return ' '.join(parts)
    
    def format_mla(self, entry_type, authors, year, title, fields):
        """MLA format."""
        parts = []
        
        if authors:
            parts.append(f'{authors}.')
        
        parts.append(f'"{title}."')
        
        if entry_type == 'article' and 'journal' in fields:
            parts.append(f"{fields['journal']},")
            if 'volume' in fields:
                parts.append(f"vol. {fields['volume']},")
            if 'number' in fields:
                parts.append(f"no. {fields['number']},")
            parts.append(f"{year},")
            if 'pages' in fields:
                parts.append(f"pp. {fields['pages']}.")
        else:
            if 'publisher' in fields:
                parts.append(f"{fields['publisher']}, {year}.")
        
        return ' '.join(parts)
    
    def format_chicago(self, entry_type, authors, year, title, fields):
        """Chicago format."""
        parts = []
        
        if authors:
            parts.append(f"{authors}.")
        
        parts.append(f'{year}. "{title}."')
        
        if entry_type == 'article' and 'journal' in fields:
            journal_part = fields['journal']
            if 'volume' in fields:
                journal_part += f" {fields['volume']}"
            if 'number' in fields:
                journal_part += f", no. {fields['number']}"
            if 'pages' in fields:
                journal_part += f": {fields['pages']}"
            parts.append(journal_part + ".")
        else:
            if 'publisher' in fields:
                parts.append(f"{fields['publisher']}.")
        
        return ' '.join(parts)
    
    def format_harvard(self, entry_type, authors, year, title, fields):
        """Harvard format."""
        return self.format_apa(entry_type, authors, year, title, fields)
    
    def format_ieee(self, entry_type, authors, year, title, fields):
        """IEEE format."""
        parts = []
        
        if authors:
            parts.append(f'{authors},')
        
        parts.append(f'"{title},"')
        
        if entry_type == 'article' and 'journal' in fields:
            journal_part = fields['journal']
            if 'volume' in fields:
                journal_part += f", vol. {fields['volume']}"
            if 'number' in fields:
                journal_part += f", no. {fields['number']}"
            if 'pages' in fields:
                journal_part += f", pp. {fields['pages']}"
            parts.append(journal_part + f", {year}.")
        else:
            if 'publisher' in fields:
                parts.append(f"{fields['publisher']}, {year}.")
        
        return ' '.join(parts)
    
    def format_vancouver(self, entry_type, authors, year, title, fields):
        """Vancouver format."""
        parts = []
        
        if authors:
            parts.append(f"{authors}.")
        
        parts.append(f"{title}.")
        
        if entry_type == 'article' and 'journal' in fields:
            parts.append(f"{fields['journal']}.")
            if 'year' in fields:
                date_str = year
                if 'month' in fields:
                    date_str = f"{year} {fields['month']}"
                parts.append(f"{date_str};")
            if 'volume' in fields:
                vol_str = fields['volume']
                if 'number' in fields:
                    vol_str += f"({fields['number']})"
                if 'pages' in fields:
                    vol_str += f":{fields['pages']}"
                parts.append(vol_str + ".")
        else:
            if 'publisher' in fields:
                parts.append(f"{fields['publisher']}; {year}.")
        
        return ' '.join(parts)
    
    def format_ama(self, entry_type, authors, year, title, fields):
        """AMA format."""
        parts = []
        
        if authors:
            parts.append(f"{authors}.")
        
        parts.append(f"{title}.")
        
        if entry_type == 'article' and 'journal' in fields:
            journal = fields['journal']
            parts.append(f"{journal}.")
            if 'year' in fields:
                parts.append(f"{year};")
            if 'volume' in fields:
                vol_str = fields['volume']
                if 'number' in fields:
                    vol_str += f"({fields['number']})"
                if 'pages' in fields:
                    vol_str += f":{fields['pages']}"
                parts.append(vol_str + ".")
        else:
            if 'publisher' in fields:
                parts.append(f"{fields['publisher']}; {year}.")
        
        return ' '.join(parts)
    
    def format_acs(self, entry_type, authors, year, title, fields):
        """ACS format."""
        parts = []
        
        if authors:
            parts.append(f"{authors}.")
        
        parts.append(f"{title}.")
        
        if entry_type == 'article' and 'journal' in fields:
            journal_part = fields['journal']
            if 'year' in fields:
                journal_part += f" {year}"
            if 'volume' in fields:
                journal_part += f", {fields['volume']}"
            if 'pages' in fields:
                journal_part += f", {fields['pages']}"
            parts.append(journal_part + ".")
        else:
            if 'publisher' in fields:
                parts.append(f"{fields['publisher']}: {year}.")
        
        return ' '.join(parts)
    
    def format_nature(self, entry_type, authors, year, title, fields):
        """Nature format."""
        parts = []
        
        if authors:
            parts.append(f"{authors}.")
        
        parts.append(f"{title}.")
        
        if entry_type == 'article' and 'journal' in fields:
            journal = fields['journal']
            vol_str = journal
            if 'volume' in fields:
                vol_str += f" {fields['volume']},"
            if 'pages' in fields:
                vol_str += f" {fields['pages']}"
            vol_str += f" ({year})"
            parts.append(vol_str + ".")
        else:
            if 'publisher' in fields:
                parts.append(f"({fields['publisher']}, {year}).")
        
        return ' '.join(parts)
    
    def wrap_text(self, text, max_width_chars, first_line_indent=0, subsequent_indent=0):
        """Wrap text to fit within max width with optional indentation."""
        words = text.split()
        lines = []
        
        # Adjust max width for first line
        first_line_max = max_width_chars - first_line_indent
        subsequent_max = max_width_chars - subsequent_indent
        
        current_line = []
        current_length = 0
        is_first_line = True
        
        for word in words:
            word_length = len(word)
            max_line_length = first_line_max if is_first_line else subsequent_max
            
            if current_length + word_length + len(current_line) <= max_line_length:
                current_line.append(word)
                current_length += word_length
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    is_first_line = False
                current_line = [word]
                current_length = word_length
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
    def get_font_family(self):
        """Get the font family based on selection."""
        font_map = {
            'serif': 'serif',
            'sans-serif': 'sans-serif',
            'monospace': 'monospace',
            'times': 'Times New Roman, serif',
            'arial': 'Arial, sans-serif',
            'helvetica': 'Helvetica, sans-serif',
            'georgia': 'Georgia, serif',
            'palatino': 'Palatino Linotype, serif',
            'garamond': 'Garamond, serif',
            'courier': 'Courier New, monospace',
            'verdana': 'Verdana, sans-serif',
            'trebuchet': 'Trebuchet MS, sans-serif'
        }
        return font_map.get(self.options.font_family, 'serif')
    
#     # LaTeX Backend Methods
    
#     def add_references_latex(self, formatted_refs, entries):
#         """Add references using LaTeX rendering."""
#         latex_content = self.build_latex_bibliography(formatted_refs, entries)
        
#         # Debug: show generated LaTeX
#         inkex.utils.debug("Generated LaTeX for bibliography:")
#         inkex.utils.debug(latex_content[:500])
        
#         # Render LaTeX to SVG
#         svg_file = self.render_latex_to_svg(latex_content)
#         self.import_latex_svg(svg_file)
    
#     def build_latex_bibliography(self, formatted_refs, entries):
#         """Build LaTeX document for bibliography."""
        
#         # Default packages
#         packages = r"""\usepackage[utf8]{inputenc}
# \usepackage{geometry}
# \geometry{paperwidth=30in, paperheight=30in, margin=0.5in}"""
        
#         # Add user packages
#         if self.options.latex_packages:
#             packages += "\n" + self.options.latex_packages
        
#         # Add user preamble
#         if self.options.latex_preamble:
#             packages += "\n" + self.options.latex_preamble
        
#         # Build bibliography content
#         bib_items = []
        
#         # Add title if needed
#         if self.options.show_title:
#             title_size = self.get_latex_font_size(self.options.font_size + 2)
#             bib_items.append(f"\\noindent{{{title_size}\\textbf{{{self.escape_latex(self.options.title_text)}}}}}\\\\[0.5em]")
        
#         # Add each reference
#         font_size_cmd = self.get_latex_font_size(self.options.font_size)
        
#         for i, ref in enumerate(formatted_refs, 1):
#             marker = self.get_numbering_marker(i)
            
#             if self.options.hanging_indent:
#                 # Use hanging indent environment
#                 indent_pt = self.options.indent_size * 0.75  # Convert px to pt approximately
#                 ref_text = f"{marker} {ref}" if marker else ref
#                 bib_items.append(
#                     f"\\hangindent={indent_pt}pt\n"
#                     f"\\noindent {font_size_cmd}{self.escape_latex(ref_text)}\\\\[{self.options.line_spacing - 1}em]"
#                 )
#             else:
#                 ref_text = f"{marker} {ref}" if marker else ref
#                 bib_items.append(f"\\noindent {font_size_cmd}{self.escape_latex(ref_text)}\\\\[{self.options.line_spacing - 1}em]")
        
#         content = "\n\n".join(bib_items)
        
#         # Build document
#         document = rf"""\documentclass{{article}}
# {packages}
# \pagestyle{{empty}}
# \setlength{{\parindent}}{{0pt}}
# \begin{{document}}
# {content}
# \end{{document}}
# """
        
#         return document
    
#     def get_latex_font_size(self, size):
#         """Convert pixel font size to LaTeX size command."""
#         if size <= 8:
#             return r"\tiny"
#         elif size <= 10:
#             return r"\scriptsize"
#         elif size <= 11:
#             return r"\footnotesize"
#         elif size <= 12:
#             return r"\small"
#         elif size <= 14:
#             return r"\normalsize"
#         elif size <= 17:
#             return r"\large"
#         elif size <= 20:
#             return r"\Large"
#         elif size <= 25:
#             return r"\LARGE"
#         else:
#             return r"\huge"
    
    # def escape_latex(self, text):
    #     """Escape special LaTeX characters."""
    #     if not text:
    #         return ""
    #     replacements = {
    #         '\\': r'\textbackslash{}',
    #         '&': r'\&',
    #         '%': r'\%',
    #         '$': r'\$',
    #         '#': r'\#',
    #         '_': r'\_',
    #         '{': r'\{',
    #         '}': r'\}',
    #         '~': r'\textasciitilde{}',
    #         '^': r'\textasciicircum{}'
    #     }
    #     for old, new in replacements.items():
    #         text = text.replace(old, new)
    #     return text
    
    # def render_latex_to_svg(self, latex_content):
    #     """Compile LaTeX to PDF then convert to SVG."""
    #     tmpdir = tempfile.mkdtemp(prefix='inkscape_bibtex_')
        
    #     try:
    #         tex_file = os.path.join(tmpdir, 'bibliography.tex')
    #         pdf_file = os.path.join(tmpdir, 'bibliography.pdf')
    #         svg_file = os.path.join(tmpdir, 'bibliography.svg')
            
    #         # Write LaTeX file
    #         with open(tex_file, 'w', encoding='utf-8') as f:
    #             f.write(latex_content)
            
    #         inkex.utils.debug(f"LaTeX file written to: {tex_file}")
            
    #         # Compile LaTeX to PDF
    #         result = subprocess.run(
    #             ['pdflatex', '-interaction=nonstopmode', '-halt-on-error', 
    #              '-output-directory', tmpdir, tex_file],
    #             capture_output=True,
    #             text=True,
    #             timeout=30,
    #             cwd=tmpdir
    #         )
            
    #         if result.returncode != 0 or not os.path.exists(pdf_file):
    #             error_msg = f"LaTeX compilation failed:\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    #             raise Exception(error_msg)
            
    #         inkex.utils.debug(f"PDF created: {pdf_file}")
            
    #         # Convert PDF to SVG
    #         svg_created = False
            
    #         # Method 1: Using inkex.command.inkscape
    #         try:
    #             inkex.command.inkscape(
    #                 pdf_file,
    #                 export_filename=svg_file,
    #                 pdf_poppler=True,
    #                 export_type='svg',
    #                 export_text_to_path=True,
    #                 export_area_drawing=True
    #             )
    #             if os.path.exists(svg_file):
    #                 svg_created = True
    #                 inkex.utils.debug("Method 1 (inkex.command) succeeded")
    #         except Exception as e:
    #             inkex.utils.debug(f"Method 1 failed: {e}")
            
    #         # Method 2: Direct subprocess call
    #         if not svg_created:
    #             try:
    #                 result = subprocess.run(
    #                     ['inkscape', pdf_file, '--export-filename=' + svg_file,
    #                      '--pdf-poppler', '--export-type=svg', '--export-text-to-path',
    #                      '--export-area-drawing'],
    #                     capture_output=True,
    #                     text=True,
    #                     timeout=30
    #                 )
    #                 if os.path.exists(svg_file):
    #                     svg_created = True
    #                     inkex.utils.debug("Method 2 (subprocess) succeeded")
    #             except Exception as e:
    #                 inkex.utils.debug(f"Method 2 failed: {e}")
            
    #         # Method 3: Simple conversion
    #         if not svg_created:
    #             try:
    #                 result = subprocess.run(
    #                     ['inkscape', pdf_file, '--export-filename=' + svg_file],
    #                     capture_output=True,
    #                     text=True,
    #                     timeout=30
    #                 )
    #                 if os.path.exists(svg_file):
    #                     svg_created = True
    #                     inkex.utils.debug("Method 3 (simple) succeeded")
    #             except Exception as e:
    #                 inkex.utils.debug(f"Method 3 failed: {e}")
            
    #         if not svg_created:
    #             raise Exception(f"PDF to SVG conversion failed. PDF exists at: {pdf_file}")
            
    #         inkex.utils.debug(f"SVG created: {svg_file}")
            
    #         # Copy SVG to avoid temp directory issues
    #         final_svg = os.path.join(tmpdir, 'bibliography_final.svg')
    #         shutil.copy2(svg_file, final_svg)
            
    #         return final_svg
            
    #     except Exception as e:
    #         inkex.utils.debug(f"Temp directory preserved at: {tmpdir}")
    #         raise e
    
    # def import_latex_svg(self, svg_file):
    #     """Import rendered LaTeX SVG into document."""
    #     try:
    #         # Parse the SVG file
    #         tree = etree.parse(svg_file)
    #         root = tree.getroot()
            
    #         # Create a group for the imported content
    #         group = Group()
    #         group.set('id', self.svg.get_unique_id('references-latex'))
            
    #         # Import all elements from the SVG
    #         svg_ns = {'svg': 'http://www.w3.org/2000/svg'}
    #         for element in root:
    #             tag = etree.QName(element.tag).localname
    #             if tag not in ['metadata', 'defs']:
    #                 group.append(element)
            
    #         # Import defs if they exist
    #         defs = root.find('.//svg:defs', svg_ns)
    #         if defs is not None:
    #             doc_defs = self.svg.defs
    #             for def_element in defs:
    #                 doc_defs.append(def_element)
            
    #         # Position the group
    #         x_pos, y_pos = self.get_position()
    #         transform = Transform()
    #         transform.add_translate(x_pos, y_pos)
    #         group.transform = transform
            
    #         # Add to current layer
    #         self.svg.get_current_layer().append(group)
            
    #         inkex.utils.debug("SVG imported successfully")
            
    #     except Exception as e:
    #         inkex.errormsg(f"Error importing SVG: {str(e)}")
    #         raise
    
    # Inkscape Backend Methods
    
    def add_references_to_document(self, formatted_refs):
        """Add formatted references to the Inkscape document at specified position."""
        # Create a group for all references
        group = Group()
        group.set('id', self.svg.get_unique_id('references'))
        
        font_size = self.options.font_size
        line_height = font_size * self.options.line_spacing
        font_family = self.get_font_family()
        
        # Calculate approximate character width
        char_width = font_size * 0.6
        max_chars = int(self.options.max_width / char_width)
        
        # Calculate marker width for hanging indent
        sample_marker = self.get_numbering_marker(len(formatted_refs))
        marker_chars = len(sample_marker) + 1
        
        # Create all text elements
        all_lines = []
        
        # Title
        if self.options.show_title:
            all_lines.append({
                'text': self.options.title_text,
                'is_title': True,
                'indent': 0
            })
        
        # Process each reference
        for i, ref in enumerate(formatted_refs, 1):
            marker = self.get_numbering_marker(i)
            full_text = f"{marker} {ref}" if marker else ref
            
            # Calculate indents
            if self.options.hanging_indent and marker:
                first_indent = 0
                subsequent_indent = marker_chars
            else:
                first_indent = 0
                subsequent_indent = 0
            
            wrapped_lines = self.wrap_text(full_text, max_chars, first_indent, subsequent_indent)
            
            for j, line in enumerate(wrapped_lines):
                all_lines.append({
                    'text': line,
                    'is_title': False,
                    'is_first': j == 0,
                    'indent': 0 if j == 0 else (self.options.indent_size if self.options.hanging_indent else 0)
                })
        
        # Calculate total height
        total_height = len(all_lines) * line_height + self.options.box_padding * 2
        
        # Get position
        x_pos, y_pos = self.get_position()
        
        # Add background box if requested
        if self.options.add_box:
            box = Rectangle()
            box.set('x', str(x_pos - self.options.box_padding))
            box.set('y', str(y_pos - self.options.box_padding))
            box.set('width', str(self.options.max_width + self.options.box_padding * 2))
            box.set('height', str(total_height))
            box.style = {
                'fill': "#ffffff",
                'fill-opacity': '1',
                'stroke': '#cccccc',
                'stroke-width': '1'
            }
            group.add(box)
        
        # Add text elements
        current_y = y_pos + line_height
        
        for line_data in all_lines:
            text_elem = TextElement()
            x_position = x_pos + line_data.get('indent', 0)
            text_elem.set('x', str(x_position))
            text_elem.set('y', str(current_y))
            
            if line_data['is_title']:
                text_elem.style = {
                    'font-size': f'{font_size + 2}px',
                    'font-weight': 'bold',
                    'font-family': font_family,
                    'fill': '#000000'
                }
            else:
                text_elem.style = {
                    'font-size': f'{font_size}px',
                    'font-family': font_family,
                    'fill': '#000000'
                }
            
            text_elem.text = line_data['text']
            group.add(text_elem)
            
            current_y += line_height
        
        # Add the group to the current layer
        self.svg.get_current_layer().add(group)


if __name__ == '__main__':
    BibTeXLoader().run()