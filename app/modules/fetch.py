import datetime
import pdfplumber
from pdf2image import convert_from_bytes
import pytesseract
import io
import os
from PyPDF2 import PdfReader
import sys
import boto3
import botocore.session
from app.utils.utility_functions import Utils
from typing import Dict, Optional, List, Tuple
from dotenv import load_dotenv
from langchain.schema import Document
from app.modules.embeddings import handle_embeddings
from PIL import Image
import warnings
import logging

# Configure logging to capture and discard unwanted warnings
os.environ['PDFMINER_STRICT'] = '0'  # Suppress pdfminer strict mode warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdf2image").setLevel(logging.ERROR)

# Suppress specific warnings
warnings.filterwarnings("ignore", message=".*CropBox.*")
warnings.filterwarnings("ignore", message=".*MediaBox.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

load_dotenv()

class S3FileHandler:
    def __init__(self):
        self.bucket_name = os.getenv("BUCKET_NAME_EXP")
        self.utils = Utils()
        self.s3_client = self._create_s3_client()
        self.embeddings = handle_embeddings()
 
    def _create_s3_client(self) -> boto3.client:
        session = botocore.session.get_session()
        session.set_config_variable('tls_versions', 'TLSv1.2')
        return boto3.client("s3", config=boto3.session.Config(signature_version='s3v4'))
 
    def read_s3_file(self, object_name: str) -> Optional[str]:
        """Reads an S3 file and returns its content as a string."""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_name)
            content = response["Body"].read().decode("utf-8")
            return content
        except Exception as e:
            print(f"Error accessing S3 file: {e}")
            return None
 
    def fetch_data(self) -> List[Document]:
        """Fetches Markdown data from S3 and wraps it in a LangChain Document."""
        object_name = os.getenv("S3_OBJECT_NAME_EXP")
        if not object_name:
            print(f"⚠️ S3_OBJECT_NAME_EXP environment variable not set. Please set this to the path of your processed data.")
            return []
            
        # Check if file exists before attempting to read it
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_name)
        except Exception as e:
            if "NoSuchKey" in str(e) or "Not Found" in str(e):
                print(f"⚠️ File '{object_name}' does not exist in bucket '{self.bucket_name}'.")
                print(f"⚠️ You need to process PDF files first using the /inject_bronze_to_silver endpoint.")
                print(f"⚠️ Expected path: s3://{self.bucket_name}/{object_name}")
            else:
                print(f"Error checking S3 file existence: {e}")
            return []
        
        # Now read the file content
        content = self.read_s3_file(object_name)
        if not content:
            return []
            
        print(f"✅ Successfully fetched data from s3://{self.bucket_name}/{object_name} ({len(content)} characters)")
        return [Document(page_content=content)]
 
    def process_s3_data(self) -> Dict:
        """Processes the S3 data by embedding its content."""
        try:
            print(f"Starting embedding process...")
            
            # Step 1: Create/verify OpenSearch index
            if not self.embeddings.create_index_body(self.embeddings.index_name):
                print(f"❌ Failed to create or verify the OpenSearch index '{self.embeddings.index_name}'")
                return {
                    "status": "error",
                    "message": "Failed to create/verify index"
                }
                
            print(f"✅ OpenSearch index ready")
            
            # Step 2: Fetch data from S3
            print(f"Fetching text data from S3...")
            documents = self.fetch_data()
            if not documents:
                print(f"❌ No documents to embed - Check that files are in the correct S3 location")
                return {
                    "status": "error",
                    "message": "No documents retrieved from S3"
                }
                
            print(f"✅ Retrieved {len(documents)} documents with {sum(len(doc.page_content) for doc in documents)} total characters")
            
            # Step 3: Create embeddings and store in OpenSearch
            print(f"Creating embeddings and storing in OpenSearch...")
            success_count = self.embeddings.embedding_docs(
                self.embeddings.vectorstore,
                documents
            )
            
            if success_count > 0:
                print(f"✅ Successfully embedded {success_count} document chunks")
                return {
                    "status": "success",
                    "message": f"Successfully embedded {success_count} document chunks",
                    "documents_processed": len(documents)
                }
            else:
                print(f"❌ Failed to embed any documents")
                return {
                    "status": "error",
                    "message": "Failed to embed documents"
                }
                
        except Exception as e:
            print(f"❌ Error processing S3 data: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def extract_text_from_pdf(self, data: bytes) -> str:
        """Extract text from PDF using multiple methods for best results."""
        # First, try to extract with pdfplumber which handles most PDFs well
        text = self._extract_with_pdfplumber(data)
        
        # Log the results
        if text.strip():
            print(f"✅ Successfully extracted {len(text.strip())} characters using pdfplumber")
        else:
            print("⚠️ pdfplumber extraction yielded no text, check PDF format")
        
        return text
        
    def _extract_with_pdfplumber(self, data: bytes) -> str:
        """Extract text from PDF using pdfplumber with performance optimizations."""
        text = ""
        try:
            # Use a memory-efficient approach
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                # Get the total number of pages for reporting
                total_pages = len(pdf.pages)
                
                # Performance optimization: only log every 10 pages for large documents
                verbose_logging = total_pages <= 50  # Only show detailed logs for smaller docs
                print(f"Processing PDF with {total_pages} pages{' (detailed logging enabled)' if verbose_logging else ' (summary logging enabled)'}")
                
                # Track stats for summary reporting
                text_pages = 0
                table_pages = 0
                empty_pages = 0
                
                for i, page in enumerate(pdf.pages):
                    page_num = i + 1
                    try:
                        # Extract text with pdfplumber
                        page_text = page.extract_text()
                        
                        if page_text and len(page_text.strip()) > 20:  # Ensure meaningful text
                            text += page_text + "\n\n"  # Add double newline between pages
                            text_pages += 1
                            if verbose_logging or page_num % 10 == 0 or page_num == 1 or page_num == total_pages:
                                print(f"✅ Page {page_num}/{total_pages}: Extracted text successfully")
                        else:
                            # Performance optimization: only extract tables when needed
                            tables = page.extract_tables()
                            if tables:
                                table_text = self._format_tables(tables)
                                if table_text:
                                    text += f"PAGE {page_num} TABLES:\n{table_text}\n\n"
                                    table_pages += 1
                                    if verbose_logging or page_num % 10 == 0 or page_num == 1 or page_num == total_pages:
                                        print(f"✅ Page {page_num}/{total_pages}: Extracted {len(tables)} tables")
                                    continue
                            
                            # If no text or tables, note the empty page
                            empty_pages += 1
                            if verbose_logging or page_num % 10 == 0 or page_num == 1 or page_num == total_pages:
                                print(f"⚠️ Page {page_num}/{total_pages}: No extractable text found")
                    except Exception as e:
                        empty_pages += 1
                        print(f"❌ Error processing page {page_num}/{total_pages}: {str(e)}")
                
                # Print summary stats
                if not verbose_logging:
                    print(f"📊 Summary: {text_pages} pages with text, {table_pages} pages with tables, {empty_pages} empty/error pages")
        except Exception as e:
            print(f"❌ Error opening PDF with pdfplumber: {str(e)}")
        
        return text
    
    def _format_tables(self, tables: List) -> str:
        """Format tables extracted by pdfplumber into readable text."""
        if not tables:
            return ""
            
        result = []
        for i, table in enumerate(tables):
            if not table:
                continue
                
            # Convert the table to text
            table_text = f"Table {i+1}:\n"
            for row in table:
                # Filter out None values and empty strings
                formatted_row = [str(cell) if cell is not None else "" for cell in row]
                # Join with pipe separator for readability
                table_text += " | ".join(formatted_row) + "\n"
            
            result.append(table_text)
            
        return "\n\n".join(result)
    
    def _is_poppler_installed(self) -> bool:
        """Check if poppler is installed for PDF to image conversion."""
        try:
            import subprocess
            result = subprocess.run(["pdftoppm", "-v"], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE, 
                                   check=False)
            return result.returncode == 0
        except:
            return False

    def process_all_pdfs(
        self,
        input_bucket: str = "exp-dev-agent-platform-bronze-layer",
        output_bucket: str = "exp-dev-agent-platform-silver-layer",
        output_key: str = "processed_data/coda_documents.txt",
        full_data_key: str = "whole_data/full_coda_data.txt", 
        prefix: str = "coda_document/",
        max_files: int = None  # Optional limit on number of files to process
    ):
        """Process PDF files from S3 bucket with performance optimizations."""
        start_time = datetime.datetime.now()
        print(f"🚀 Started processing at {start_time.strftime('%H:%M:%S')}")
        print(f"Scanning bucket: {input_bucket} with prefix: {prefix} for PDF files only")
        
        # Performance optimization: List all files first, then process
        try:
            # Use a pagination filter to only list PDF files
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=input_bucket,
                Prefix=prefix
            )

            # Collect all PDF keys to process
            pdf_keys = []
            for page in pages:
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # Only include PDF files
                    if key.lower().endswith('.pdf'):
                        pdf_keys.append(key)
            
            if max_files and len(pdf_keys) > max_files:
                print(f"⚠️ Limiting processing to first {max_files} of {len(pdf_keys)} PDF files found")
                pdf_keys = pdf_keys[:max_files]
            else:
                print(f"📁 Found {len(pdf_keys)} PDF files to process")
                
            if not pdf_keys:
                print("❌ No PDF files found. Check the bucket and prefix.")
                return
                
            # Process PDF files in batches for better memory management
            combined_text = []
            file_count = 0
            success_count = 0
            error_count = 0
            
            # Process files more efficiently
            for idx, key in enumerate(pdf_keys):
                file_count += 1
                file_start_time = datetime.datetime.now()
                print(f"\n{'='*60}\nProcessing PDF {file_count}/{len(pdf_keys)}: {key}\n{'='*60}")
                try:
                    # Get the file
                    response = self.s3_client.get_object(Bucket=input_bucket, Key=key)
                    binary_data = response['Body'].read()
                    file_size_mb = len(binary_data) / (1024 * 1024)
                    print(f"📄 File size: {file_size_mb:.2f} MB")
                    
                    # Extract text using our enhanced method
                    text = self.extract_text_from_pdf(binary_data)
                    
                    # Free up memory
                    del binary_data
                    
                    if text.strip():
                        # Add document metadata and extracted text
                        doc_header = f"--- DOCUMENT: {key} ---\n"
                        doc_metadata = f"Source: {input_bucket}/{key}\nProcessed: {datetime.datetime.now().isoformat()}\n\n"
                        combined_text.append(doc_header + doc_metadata + text)
                        success_count += 1
                        
                        # Calculate processing time
                        file_duration = datetime.datetime.now() - file_start_time
                        print(f"✅ Successfully processed: {key} ({len(text)} chars extracted in {file_duration.total_seconds():.1f} seconds)")
                    else:
                        # Record failure but don't add to combined text
                        error_count += 1
                        print(f"❌ No text extracted from: {key}")
                except Exception as e:
                    error_count += 1
                    print(f"❌ Error processing {key}: {str(e)}")
                
                # Print progress
                progress = (idx + 1) / len(pdf_keys) * 100
                print(f"📊 Overall progress: {progress:.1f}% complete")

            # Combine all text for this batch
            final_text = "\n\n".join(combined_text)

            # Total processing time
            total_duration = datetime.datetime.now() - start_time
            minutes, seconds = divmod(total_duration.total_seconds(), 60)

            print(f"\n{'='*80}")
            print(f"PDF Processing Summary:")
            print(f"  - Total files found: {file_count}")
            print(f"  - Successfully processed: {success_count}")
            print(f"  - Failed: {error_count}")
            print(f"  - Total text extracted: {len(final_text)} characters")
            print(f"  - Total processing time: {int(minutes)} minutes, {int(seconds)} seconds")
            print(f"{'='*80}\n")

            if not final_text.strip():
                print("⚠️ No text extracted from any PDF files.")
                return
                
            # 1. Upload to the regular output location (replacing existing content)
            self.s3_client.put_object(
                Bucket=output_bucket,
                Key=output_key,
                Body=final_text.encode('utf-8')
            )
            print(f"✅ Content saved to: s3://{output_bucket}/{output_key}")
            
            # 2. Create a file with the current timestamp in the batch folder
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            batch_file_key = f"whole_data/batches/batch_{timestamp}.txt"
            batch_header = f"--- BATCH PROCESSED AT {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            batch_stats = f"Files processed: {file_count}, Success: {success_count}, Failed: {error_count}\n\n"
            batch_content = batch_header + batch_stats + final_text
            
            try:
                # Upload this batch as a separate file
                self.s3_client.put_object(
                    Bucket=output_bucket,
                    Key=batch_file_key,
                    Body=batch_content.encode('utf-8')
                )
                print(f"✅ Batch saved to: s3://{output_bucket}/{batch_file_key}")
                
                # 3. Update the pointer file to include this new batch
                pointer_content = f"{batch_file_key}\n"
                
                try:
                    # Check if pointer file exists
                    pointer_key = "whole_data/batch_list.txt"
                    response = self.s3_client.get_object(
                        Bucket=output_bucket,
                        Key=pointer_key
                    )
                    existing_pointer = response["Body"].read().decode("utf-8")
                    # Add new batch to existing pointer file
                    updated_pointer = existing_pointer + pointer_content
                except:
                    # Pointer file doesn't exist yet
                    updated_pointer = pointer_content
                
                # Save the updated pointer file
                self.s3_client.put_object(
                    Bucket=output_bucket,
                    Key=pointer_key,
                    Body=updated_pointer.encode('utf-8')
                )
                print(f"✅ Batch list updated: s3://{output_bucket}/{pointer_key}")
                
                # 4. For download convenience, also upload a small update to the "latest" file
                latest_key = "whole_data/latest_batch.txt"
                self.s3_client.put_object(
                    Bucket=output_bucket,
                    Key=latest_key,
                    Body=f"Latest batch: {batch_file_key} processed at {datetime.datetime.now().isoformat()}".encode('utf-8')
                )
                
                print(f"✅ Processing complete. Total time: {int(minutes)} minutes, {int(seconds)} seconds")
                    
            except Exception as e:
                print(f"❌ Error saving batch files: {str(e)}")
                print(f"   The regular output file was still created successfully.")
                
        except Exception as e:
            print(f"❌ Fatal error during processing: {str(e)}")
            return

    def delete_s3_prefix(self, bucket_name, prefix):
        """
        Delete objects in an S3 bucket with a specific prefix,
        but preserve the folder structure.
        """
        try:
            # List objects with the given prefix
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=bucket_name,
                Prefix=prefix
            )
            
            # Create a list of objects to delete, excluding folder objects
            delete_list = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        # Skip the folder object itself (usually ends with a slash or is exactly the prefix)
                        if key == prefix or key.endswith('/'):
                            print(f"Preserving folder structure: {key}")
                            continue
                        # Only delete files inside the folder, not the folder itself
                        delete_list.append({'Key': key})
            
            if not delete_list:
                print(f"No objects found with prefix '{prefix}' in bucket '{bucket_name}'")
                return
            
            # Delete objects in batches of 1000 (S3 API limit)
            batch_size = 1000
            for i in range(0, len(delete_list), batch_size):
                batch = delete_list[i:i + batch_size]
                response = self.s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': batch}
                )
                deleted = len(response.get('Deleted', []))
                errors = len(response.get('Errors', []))
                print(f"Deleted {deleted} files inside '{prefix}', encountered {errors} errors")
            
            return f"Successfully deleted {len(delete_list)} files inside '{prefix}' while preserving folder structure"
        except Exception as e:
            print(f"Error deleting objects with prefix '{prefix}': {str(e)}")
            raise

        