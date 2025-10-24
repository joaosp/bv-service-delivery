"""
Document Download Extractor

Handles downloading of documents, attachments, and files from Salesforce.
Supports multiple download methods with fallback mechanisms.
"""

import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .base import SalesforceBase


class DocumentExtractor(SalesforceBase):
    """Extracts and downloads documents from Salesforce"""
    
    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        super().__init__(org_username)
        self.documents_data = []
        self.download_stats = {
            "attempted": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0
        }
    
    def get_content_documents(self, entity_id: str) -> List[Dict]:
        """
        Get all documents linked to an entity (Opportunity, Account, etc.)
        
        Args:
            entity_id: Salesforce record ID
            
        Returns:
            List of ContentDocument records
        """
        self.log_info("Fetching document list")
        
        query = f"""
        SELECT Id, ContentDocumentId, ContentDocument.Title,
               ContentDocument.FileType, ContentDocument.FileExtension,
               ContentDocument.ContentSize, ContentDocument.CreatedDate,
               ContentDocument.LatestPublishedVersionId,
               ContentDocument.CreatedBy.Name, ContentDocument.Description
        FROM ContentDocumentLink
        WHERE LinkedEntityId = '{entity_id}'
        ORDER BY ContentDocument.CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            self.documents_data = result["records"]
            self.log_success(f"Found {len(self.documents_data)} documents")
            
            # Categorize documents
            doc_types = self._categorize_documents(self.documents_data)
            self.log_info("Document types:")
            for ext, count in sorted(doc_types.items()):
                print(f"   - {ext}: {count} file(s)")
            
            return self.documents_data
        
        self.log_info("No documents found")
        return []
    
    def _categorize_documents(self, documents: List[Dict]) -> Dict[str, int]:
        """Categorize documents by file extension"""
        doc_types = {}
        for doc in documents:
            ext = doc.get("ContentDocument", {}).get("FileExtension", "unknown").lower()
            doc_types[ext] = doc_types.get(ext, 0) + 1
        return doc_types
    
    def _determine_folder(self, title: str, extension: str) -> str:
        """
        Determine appropriate folder based on document title and extension
        
        Args:
            title: Document title
            extension: File extension
            
        Returns:
            Folder name for the document
        """
        title_lower = title.lower()
        ext_lower = extension.lower()
        
        # PDF categorization
        if ext_lower == "pdf":
            if any(keyword in title_lower for keyword in ["quote", "proposal", "pricing"]):
                return "quotes"
            elif any(keyword in title_lower for keyword in ["contract", "loa", "letter", "agreement", "bof"]):
                return "contracts"
            else:
                return "pdfs"
        
        # Office documents
        elif ext_lower in ["xlsx", "xls", "csv"]:
            return "spreadsheets"
        elif ext_lower in ["docx", "doc"]:
            if "contract" in title_lower:
                return "contracts"
            else:
                return "documents"
        
        # Email files
        elif ext_lower in ["msg", "eml"]:
            return "emails"
        
        # Images
        elif ext_lower in ["png", "jpg", "jpeg", "gif", "bmp", "svg"]:
            return "images"
        
        # Default
        else:
            return "other"
    
    def _clean_filename(self, filename: str, max_length: int = 100) -> str:
        """
        Clean filename for safe file system storage
        
        Args:
            filename: Original filename
            max_length: Maximum filename length
            
        Returns:
            Cleaned filename
        """
        # Remove or replace invalid characters
        safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        safe_filename = re.sub(r'[^\w\s\-_.]', '', safe_filename)
        safe_filename = re.sub(r'\s+', ' ', safe_filename).strip()
        
        # Truncate if too long
        if len(safe_filename) > max_length:
            name, ext = os.path.splitext(safe_filename)
            safe_filename = name[:max_length-len(ext)] + ext
        
        return safe_filename
    
    def _download_via_rest_api(self, version_id: str, filepath: Path) -> bool:
        """
        Download document using REST API endpoint
        
        Args:
            version_id: ContentVersion ID
            filepath: Target file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            api_endpoint = f"/services/data/v64.0/sobjects/ContentVersion/{version_id}/VersionData"
            # Use the new output_file parameter for binary downloads
            response = self.run_api_request(api_endpoint, method="GET", output_file=str(filepath))
            
            # For binary downloads, response will be empty bytes if successful
            if response is not None:
                return filepath.exists() and filepath.stat().st_size > 0
            
            return False
            
        except Exception as e:
            self.log_error(f"REST API download failed: {str(e)}")
            return False
    
    def _download_via_curl(self, version_id: str, filepath: Path) -> bool:
        """
        Download document using cURL with OAuth token
        
        Args:
            version_id: ContentVersion ID
            filepath: Target file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            api_endpoint = f"/services/data/v64.0/sobjects/ContentVersion/{version_id}/VersionData"
            success = self.run_curl_request(api_endpoint, str(filepath))
            
            return success and filepath.exists() and filepath.stat().st_size > 0
            
        except Exception as e:
            self.log_error(f"cURL download failed: {str(e)}")
            return False
    
    def download_document(self, doc_info: Dict, base_output_dir: Path) -> bool:
        """
        Download a single document using multiple fallback methods
        
        Args:
            doc_info: Document information from ContentDocumentLink query
            base_output_dir: Base directory for downloads
            
        Returns:
            True if download successful, False otherwise
        """
        try:
            doc = doc_info.get("ContentDocument", {})
            version_id = doc.get("LatestPublishedVersionId")
            title = doc.get("Title", "untitled")
            extension = doc.get("FileExtension", "bin").lower()
            file_size = doc.get("ContentSize", 0)
            
            if not version_id:
                self.log_error(f"No version ID for document: {title}")
                return False
            
            # Determine folder and create clean filename
            folder = self._determine_folder(title, extension)
            clean_title = self._clean_filename(title)
            filename = f"{clean_title}.{extension}"
            
            # Create folder structure
            folder_path = base_output_dir / "documents" / folder
            folder_path.mkdir(parents=True, exist_ok=True)
            
            filepath = folder_path / filename
            
            # Skip if file already exists and has size
            if filepath.exists() and filepath.stat().st_size > 0:
                self.log_info(f"Already downloaded: {filename}")
                self.download_stats["skipped"] += 1
                return True
            
            self.log_info(f"Downloading: {filename} ({self._format_file_size(file_size)})")
            self.download_stats["attempted"] += 1
            
            # Method 1: REST API
            if self._download_via_rest_api(version_id, filepath):
                self.log_success(f"Downloaded via REST API: {filename}")
                self.download_stats["successful"] += 1
                return True
            
            # Method 2: cURL fallback
            self.log_warning(f"Trying cURL method for: {filename}")
            if self._download_via_curl(version_id, filepath):
                self.log_success(f"Downloaded via cURL: {filename}")
                self.download_stats["successful"] += 1
                return True
            
            # Both methods failed
            self.log_error(f"Could not download: {filename}")
            self.download_stats["failed"] += 1
            return False
            
        except Exception as e:
            error_msg = f"Download error for {title}: {str(e)}"
            self.log_error(error_msg)
            self.download_stats["failed"] += 1
            return False
    
    def download_all_documents(self, entity_id: str, output_dir: Path) -> Dict:
        """
        Download all documents for an entity
        
        Args:
            entity_id: Salesforce record ID
            output_dir: Output directory
            
        Returns:
            Download statistics and results
        """
        # Reset stats
        self.download_stats = {"attempted": 0, "successful": 0, "failed": 0, "skipped": 0}
        
        # Get documents
        documents = self.get_content_documents(entity_id)
        
        if not documents:
            self.log_info("No documents to download")
            return self.download_stats
        
        self.log_info(f"Starting download of {len(documents)} documents...")
        
        # Create base directory structure
        self._setup_document_directories(output_dir)
        
        # Download each document
        successful_downloads = []
        failed_downloads = []
        
        for doc in documents:
            success = self.download_document(doc, output_dir)
            
            doc_title = doc.get("ContentDocument", {}).get("Title", "Unknown")
            if success:
                successful_downloads.append(doc_title)
            else:
                failed_downloads.append(doc_title)
        
        # Log summary
        total = len(documents)
        successful = self.download_stats["successful"]
        skipped = self.download_stats["skipped"]
        failed = self.download_stats["failed"]
        
        self.log_success(f"Download complete: {successful + skipped}/{total} files "
                        f"({successful} downloaded, {skipped} skipped, {failed} failed)")
        
        return {
            "stats": self.download_stats,
            "successful": successful_downloads,
            "failed": failed_downloads,
            "total_documents": total
        }
    
    def _setup_document_directories(self, base_dir: Path):
        """Create document directory structure"""
        folders = [
            "documents/quotes",
            "documents/contracts", 
            "documents/emails",
            "documents/spreadsheets",
            "documents/pdfs",
            "documents/documents",
            "documents/images",
            "documents/other"
        ]
        
        for folder in folders:
            (base_dir / folder).mkdir(parents=True, exist_ok=True)
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"
    
    def get_document_inventory(self) -> Dict:
        """
        Get detailed inventory of all documents
        
        Returns:
            Document inventory with categorization and metadata
        """
        if not self.documents_data:
            return {}
        
        inventory = {
            "total_documents": len(self.documents_data),
            "by_type": {},
            "by_size": {"small": 0, "medium": 0, "large": 0},
            "by_date": {},
            "details": []
        }
        
        for doc_link in self.documents_data:
            doc = doc_link.get("ContentDocument", {})
            
            # Extract metadata
            title = doc.get("Title", "Unknown")
            extension = doc.get("FileExtension", "unknown").lower()
            size = doc.get("ContentSize", 0)
            created_date = doc.get("CreatedDate", "")[:10]  # Just date part
            creator = doc.get("CreatedBy", {}).get("Name", "Unknown")
            
            # Categorize by type
            folder = self._determine_folder(title, extension)
            if folder not in inventory["by_type"]:
                inventory["by_type"][folder] = {"count": 0, "total_size": 0, "files": []}
            
            inventory["by_type"][folder]["count"] += 1
            inventory["by_type"][folder]["total_size"] += size
            inventory["by_type"][folder]["files"].append({
                "title": title,
                "size": size,
                "created_date": created_date
            })
            
            # Categorize by size
            if size < 1024 * 1024:  # < 1MB
                inventory["by_size"]["small"] += 1
            elif size < 10 * 1024 * 1024:  # < 10MB
                inventory["by_size"]["medium"] += 1
            else:
                inventory["by_size"]["large"] += 1
            
            # Categorize by date
            if created_date not in inventory["by_date"]:
                inventory["by_date"][created_date] = 0
            inventory["by_date"][created_date] += 1
            
            # Add to details
            inventory["details"].append({
                "title": title,
                "extension": extension,
                "folder": folder,
                "size": size,
                "size_formatted": self._format_file_size(size),
                "created_date": created_date,
                "creator": creator
            })
        
        return inventory
    
    def get_attachments(self, entity_id: str) -> List[Dict]:
        """
        Get legacy attachments (pre-ContentDocument)
        
        Args:
            entity_id: Salesforce record ID
            
        Returns:
            List of Attachment records
        """
        self.log_info("Fetching legacy attachments")
        
        query = f"""
        SELECT Id, Name, ContentType, BodyLength, CreatedDate,
               CreatedBy.Name, Description, IsPrivate
        FROM Attachment
        WHERE ParentId = '{entity_id}'
        ORDER BY CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            attachments = result["records"]
            self.log_success(f"Found {len(attachments)} legacy attachments")
            return attachments
        
        self.log_info("No legacy attachments found")
        return []
    
    def get_current_documents(self) -> List[Dict]:
        """Get currently loaded documents"""
        return self.documents_data
    
    def get_download_stats(self) -> Dict:
        """Get download statistics"""
        return self.download_stats.copy()