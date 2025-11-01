import ast
import hashlib
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
import time

# Try to import ML libraries, fall back to simpler approach if not available
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️  ML libraries not fully available, using lightweight text-based context system")


class CodebaseContextEngine:
    """
    Codebase context system that provides relevant code context for AI reviews.
    Falls back to text-based similarity if ML libraries aren't available.
    """
    
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        self.cache_dir = Path(".codebase_context_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        # Initialize ML model if available
        if ML_AVAILABLE:
            try:
                print("🧠 Loading sentence transformer model...")
                self.model = SentenceTransformer(model_name)
                self.use_embeddings = True
                print(f"✅ Loaded {model_name} for semantic similarity")
            except Exception as e:
                print(f"⚠️  Could not load ML model ({e}), using text-based similarity")
                self.use_embeddings = False
        else:
            self.use_embeddings = False
        
    def tokenize_project(self, project_root=".", exclude_patterns=None) -> List[Dict[str, Any]]:
        """Break codebase into semantic chunks"""
        if exclude_patterns is None:
            exclude_patterns = [
                "__pycache__", ".git", ".ai_review_cache", 
                "node_modules", ".venv", "*.pyc", ".codebase_context_cache",
                "*.egg-info", ".pytest_cache", ".mypy_cache", ".ruff_cache"
            ]
        
        print("🔍 Tokenizing codebase...")
        chunks = []
        
        # Find all Python files
        python_files = list(Path(project_root).rglob("*.py"))
        
        for py_file in python_files:
            if self._should_exclude(py_file, exclude_patterns):
                continue
                
            try:
                file_chunks = self._extract_semantic_chunks(py_file)
                chunks.extend(file_chunks)
            except Exception as e:
                print(f"⚠️  Could not parse {py_file}: {e}")
                continue
        
        print(f"📦 Extracted {len(chunks)} code chunks from {len(python_files)} files")
        return chunks
    
    def _should_exclude(self, filepath: Path, exclude_patterns: List[str]) -> bool:
        """Check if file should be excluded based on patterns"""
        path_str = str(filepath)
        
        for pattern in exclude_patterns:
            # Simple pattern matching
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            else:
                if pattern in path_str:
                    return True
        return False
    
    def _extract_semantic_chunks(self, filepath: Path) -> List[Dict[str, Any]]:
        """Extract functions, classes, and imports from a Python file"""
        chunks = []
        
        try:
            content = filepath.read_text(encoding='utf-8')
        except Exception:
            return chunks
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # File might have syntax errors, skip detailed parsing
            return self._create_fallback_chunk(filepath, content)
        
        # Extract imports (for understanding dependencies)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend([alias.name for alias in node.names])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module
                    for alias in node.names:
                        imports.append(f"{module_name}.{alias.name}")
        
        if imports:
            chunks.append({
                "type": "imports",
                "file": str(filepath),
                "content": f"File {filepath.name} imports: {', '.join(imports[:10])}",
                "code": "\n".join([f"import {imp}" for imp in imports[:5]]),
                "metadata": {
                    "file": str(filepath),
                    "type": "imports",
                    "line": 1
                }
            })
        
        # Extract functions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_code = self._extract_node_code(content, node)
                if func_code:
                    chunks.append({
                        "type": "function",
                        "file": str(filepath),
                        "content": f"Function {node.name} in {filepath.name}:\n{func_code[:400]}...",
                        "code": func_code,
                        "metadata": {
                            "file": str(filepath),
                            "type": "function", 
                            "name": node.name,
                            "line": node.lineno,
                            "args": [arg.arg for arg in node.args.args] if hasattr(node.args, 'args') else []
                        }
                    })
                    
            elif isinstance(node, ast.ClassDef):
                class_code = self._extract_node_code(content, node)
                if class_code:
                    chunks.append({
                        "type": "class",
                        "file": str(filepath),
                        "content": f"Class {node.name} in {filepath.name}:\n{class_code[:400]}...",
                        "code": class_code,
                        "metadata": {
                            "file": str(filepath),
                            "type": "class",
                            "name": node.name,
                            "line": node.lineno
                        }
                    })
        
        return chunks
    
    def _extract_node_code(self, content: str, node: ast.AST) -> str:
        """Extract source code for an AST node"""
        try:
            lines = content.splitlines()
            start_line = node.lineno - 1
            
            # Find end line by looking for the next function/class or end of indentation
            end_line = len(lines)
            if hasattr(node, 'end_lineno') and node.end_lineno:
                end_line = node.end_lineno
            else:
                # Fallback: find end by indentation
                base_indent = len(lines[start_line]) - len(lines[start_line].lstrip())
                for i in range(start_line + 1, len(lines)):
                    line = lines[i]
                    if line.strip() and len(line) - len(line.lstrip()) <= base_indent:
                        end_line = i
                        break
            
            return "\n".join(lines[start_line:end_line])
        except Exception:
            return ""
    
    def _create_fallback_chunk(self, filepath: Path, content: str) -> List[Dict[str, Any]]:
        """Create a simple chunk when AST parsing fails"""
        return [{
            "type": "file_overview",
            "file": str(filepath),
            "content": f"File {filepath.name} overview:\n{content[:500]}...",
            "code": content[:500],
            "metadata": {
                "file": str(filepath),
                "type": "overview",
                "line": 1
            }
        }]
    
    def generate_embeddings(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate embeddings for all code chunks"""
        cache_key = self._get_project_hash()
        cache_file = self.cache_dir / f"embeddings_{cache_key}.json"
        
        # Try to load from cache
        if cache_file.exists():
            try:
                print("🧠 Loading cached codebase embeddings...")
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                    if cached_data.get("use_embeddings") == self.use_embeddings:
                        cached_data["chunks"] = chunks  # Update chunks with latest
                        return cached_data
            except Exception:
                pass
        
        print(f"🔄 Generating context data for {len(chunks)} code chunks...")
        
        embedding_data = {
            "chunks": chunks,
            "cache_key": cache_key,
            "use_embeddings": self.use_embeddings,
            "generated_at": time.time()
        }
        
        if self.use_embeddings:
            # Generate ML embeddings
            texts = [chunk["content"] for chunk in chunks]
            try:
                embeddings = self.model.encode(texts, show_progress_bar=True)
                embedding_data["embeddings"] = embeddings.tolist()
                print("✅ Generated ML embeddings")
            except Exception as e:
                print(f"⚠️  ML embedding failed ({e}), using text similarity")
                embedding_data["use_embeddings"] = False
                self.use_embeddings = False
        
        # Cache the results
        try:
            with open(cache_file, 'w') as f:
                json.dump(embedding_data, f, indent=2)
            print(f"💾 Cached context data to {cache_file}")
        except Exception as e:
            print(f"⚠️  Could not cache embeddings: {e}")
        
        return embedding_data
    
    def find_relevant_context(self, changed_files: List[str], 
                            diff_content: str, embedding_data: Dict[str, Any], 
                            top_k: int = 5) -> List[Dict[str, Any]]:
        """Find most relevant codebase context for the changes"""
        
        if self.use_embeddings and "embeddings" in embedding_data:
            return self._find_context_with_embeddings(
                changed_files, diff_content, embedding_data, top_k
            )
        else:
            return self._find_context_with_text(
                changed_files, diff_content, embedding_data, top_k
            )
    
    def _find_context_with_embeddings(self, changed_files: List[str], 
                                    diff_content: str, embedding_data: Dict[str, Any], 
                                    top_k: int) -> List[Dict[str, Any]]:
        """Find context using ML embeddings"""
        try:
            import numpy as np
            
            # Create query from changes
            query_parts = []
            for file_path in changed_files:
                query_parts.append(f"Changes in {Path(file_path).name}")
            query_parts.append(f"Code changes: {diff_content[:1000]}")
            query_text = "\n".join(query_parts)
            
            # Get query embedding
            query_embedding = self.model.encode([query_text])
            embeddings_array = np.array(embedding_data["embeddings"])
            
            # Calculate similarity
            similarities = np.dot(embeddings_array, query_embedding.T).flatten()
            
            # Get top-k most similar chunks
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            relevant_context = []
            for idx in top_indices:
                if idx >= len(embedding_data["chunks"]):
                    continue
                    
                chunk = embedding_data["chunks"][idx]
                similarity = float(similarities[idx])
                
                if similarity > 0.2:  # Threshold for relevance
                    relevant_context.append({
                        "content": chunk["code"][:800],
                        "file": chunk["metadata"]["file"],
                        "type": chunk["metadata"]["type"],
                        "name": chunk["metadata"].get("name", ""),
                        "line": chunk["metadata"].get("line", 1),
                        "similarity": similarity
                    })
            
            return relevant_context
            
        except Exception as e:
            print(f"⚠️  Embedding similarity failed ({e}), falling back to text similarity")
            return self._find_context_with_text(changed_files, diff_content, embedding_data, top_k)
    
    def _find_context_with_text(self, changed_files: List[str], 
                              diff_content: str, embedding_data: Dict[str, Any], 
                              top_k: int) -> List[Dict[str, Any]]:
        """Find context using simple text similarity"""
        
        # Extract keywords from changes
        change_keywords = set()
        
        # Add file names
        for file_path in changed_files:
            change_keywords.add(Path(file_path).stem)
        
        # Extract function/variable names from diff
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]+\b', diff_content)
        change_keywords.update(word for word in words if len(word) > 2)
        
        # Score chunks based on keyword overlap
        scored_chunks = []
        for chunk in embedding_data["chunks"]:
            score = 0
            chunk_text = chunk["content"].lower()
            
            # Boost score for same file
            if any(Path(f).stem in chunk["file"] for f in changed_files):
                score += 10
            
            # Count keyword matches
            for keyword in change_keywords:
                if keyword.lower() in chunk_text:
                    score += 1
            
            if score > 0:
                scored_chunks.append((score, chunk))
        
        # Sort by score and take top-k
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        
        relevant_context = []
        for score, chunk in scored_chunks[:top_k]:
            relevant_context.append({
                "content": chunk["code"][:800],
                "file": chunk["metadata"]["file"],
                "type": chunk["metadata"]["type"],
                "name": chunk["metadata"].get("name", ""),
                "line": chunk["metadata"].get("line", 1),
                "similarity": score / 10.0  # Normalize score
            })
        
        return relevant_context
    
    def _get_project_hash(self) -> str:
        """Generate a hash representing the current project state"""
        # Simple hash based on file modification times
        hash_input = ""
        for py_file in Path(".").rglob("*.py"):
            if not self._should_exclude(py_file, [".git", "__pycache__"]):
                try:
                    mtime = py_file.stat().st_mtime
                    hash_input += f"{py_file}:{mtime};"
                except Exception:
                    continue
        
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
