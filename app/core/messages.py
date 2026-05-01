JOB_APPLICATION_NOT_FOUND = (
    lambda id, job_id: f"No Data found for id: {id} and job_id: {job_id}"
)
INVALID_JOB_APPLICATION_ID = lambda id: f"Invalid Job Application Id: {id}"
NO_JOB_APPLICATIONS_FOUND = f"No Job Applications Found"
DATABASE_OPERATION_FAILED = "Database operation failed"
INTERNAL_SERVER_ERROR = "Internal server error"
LOCAL = "LOCAL"
AWS_DEVELOPMENT = "AWS_DEVELOPMENT"
NO_JOB_DETAILS_FOUND = f"No Job Details Found"
INVALID_APPLICATION_ID = (
    lambda application_id: f"Invalid Application Id: {application_id}"
)
NO_RESUME_ATTRIBUTES_FOUND = "No Resume Attributes found"
ALL_RESUMES_ANALYZED = "All resumes analysis triggered successfully"
UNABLE_ANALYZE_RESUMES = "Unable to analyze Resumes"
RESUMES_ANALYZED_SUCCESSFULLY = "Resumes analyzed successfully"
NO_APPLICATIONS_PROVIDED = "No applications provided"
NO_JOB_DETAILS_FOUND_FOR_JOB_ID = lambda job_id: f"Job ID {job_id} not found"
NO_RESUME_FILE_PATH_IN_APPLICATION = "No resume file path in application"
BATCH_RESUMES_ANALYZED = "Batch resumes analysis completed"
INVALID_RESUME_LOG_ID = lambda id: f"Invalid id: {id}"
NO_RESUME_LOGS_FOUND = "No Resume Logs found"
NO_RESUME_ATTRIBUTES_FOUND = "No Resume Attributes found"
NO_RESUME_LOGS_FOUND = "No Resume Logs found"
TOKEN_EXPIRED = "Token has expired"
INVALID_TOKEN = "Invalid token"
USER_NOT_FOUND = "Token revoked or user does not exist"
FAILED_TO_CONNECT_TO_DB = "Failed to connect to database"
DB_QUERY_FAILED = (
    lambda query_type, message: f"Database query failed ({query_type}): {message}"
)
DB_INTEGRITY_ERROR = lambda message: f"Database integrity error: {message}"
RESUME_PARSE_FAILED = (
    lambda filename, message: f"Failed to parse resume '{filename}': {message}"
)
RESOURCE_NOT_FOUND_BY_IDENTIFIER = (
    lambda resource_type, identifier: f"{resource_type} not found: {identifier}"
)
RESOUNE_NOT_FOUND = lambda resource_type: f"No {resource_type} found"
RESOURCE_ALREADY_EXISTS_BY_IDENTIFIER = (
    lambda resource_type, identifier: f"{resource_type} already exists: {identifier}"
)
RESOURCE_ALREADY_EXISTS = lambda resource_type: f"{resource_type} already exists"
FILE_OPERATION_ERROR_ON_FILE = (
    lambda filename, message: f"File operation error on '{filename}': {message}"
)
FILE_OPERATION_ERROR = lambda message: f"File operation error: {message}"
DB_INIT_FAILED = lambda err: f"Failed to initialize database: {str(err)}"
DB_CREATE_TABLE_FAILED = lambda err: f"Failed to create database tables: {str(err)}"
DB_INIT_ERROR = lambda err: f"Database error during initialization: {str(err)}"
LLM_ANALYSIS_FAILED = lambda err: f"LLM analysis failed: {err}"
PARSING_FAILED = lambda err: f"Parsing failed: {str(err)}"
JSON_OBJ_NOT_FOUND = "No JSON object found in the string."
GENAI_IMPORT_ERROR = "google-generativeai library is required. Install with: pip install google-generativeai"
GEMINI_INIT_ERROR = (
    lambda model, err: f"Failed to initialize Gemini model '{model}': {str(err)}"
)
GEMINI_API_VALIDATION_ERROR = lambda err: f"Gemini API validation error: {str(err)}"
GEMINI_API_CALL_FAILED = lambda err: f"Gemini API call failed: {str(err)}"
EMPTY_STRING_ERROR = "Prompt must be a non-empty string"
FILE_NOT_FOUND = "File does not exist"
PATH_IS_NOT_A_FILE = "Path is not a file"
INVALID_FORMAT = (
    lambda supported_formats: f"Unsupported format. Supported: {supported_formats}"
)
FILE_SIZE_EXCEED = lambda max_file_size: f"File too large. Max size: {max_file_size}MB"
UNSUPPORTED_FILE_FORMAT = lambda extension: f"Unsupported file format: {extension}"
PYPDF_IMPORT_ERROR = "PyPDF2 is required for PDF parsing"
ERROR_READING_PDF_FILE = lambda err: f"Error reading PDF: {str(err)}"
PYTHON_DOCX_IMPORT_ERROR = "python-docx is required for DOCX parsing"
ERROR_READING_DOCX_FILE = lambda err: f"Error reading DOCX: {str(err)}"
NAME_NOT_FOUND = "Name not found"
EMPTY_JOB_DESCRIPTION = "Job description cannot be empty"
JOB_APPLICATION_NOT_FOUND_FOR_NAME_AND_EMAIL = (
    lambda candidate_name, email: f"No matching application found for {candidate_name} ({email})"
)
JOB_APPLICATION_NOT_FOUND_FOR_ID = (
    lambda application_id: f"No application found for ID {application_id}"
)
PDFPLUMBER_IMPORT_ERROR = "pdfplumber is required for PDF parsing"
NO_RESUME_FILES_PROVIDED = "No resume files provided for analysis"
NO_RESUME_FILES_ERROR = "No resume files provided"
RESUME_PARSED_SUCCESSFULLY = "Resume parsed successfully"
ANALYSIS_COMPLETED_AND_SAVED = "Analysis completed and saved"
FAILED_TO_SAVE_ANALYSIS = (
    lambda filename: f"Could not save analysis for '{filename}' to database"
)
FAILED_TO_SAVE_ATTRIBUTES = "Failed to save analysis attributes"
UNABLE_TO_PARSE = "Unable to parse"
ANALYSIS_PARSING_FAILED = "Analysis parsing failed"
MANUAL_REVIEW_REQUIRED = "Manual review required"
UNABLE_TO_ASSESS = "Unable to assess"
ANALYSIS_COULD_NOT_BE_PARSED = "Analysis could not be parsed properly"
TECHNICAL_ASSESSMENT = "Technical assessment"
EXPERIENCE_VERIFICATION = "Experience verification"
STANDARD_ANALYSIS_COMPLETED = "Standard analysis completed"
ANALYSIS_COMPLETED = "Analysis completed"
S3_FETCH_ERROR = lambda err: f"S3 Fetch Error: {err}"
LESS_THAN_ONE_MONTH = "Less than 1 month"
PROCESSING_FILE = (
    lambda current, total, filename: f"Processing {current}/{total}: {filename}"
)
CONFIG_FILE_NOT_FOUND = (
    lambda config_path: f"Configuration file not found at {config_path}"
)
RESUME_LOGS_DELETED_SUCCESSFULLY = "Successfully deleted resume logs"
RESUME_LOGS_DELETE_FAILED = "Unable to delete resume logs"
RESUME_BATCH_ALREADY_ANALYZED = "Analysis is already done for all resumes in this batch"
ALL_RESUMES_ALREADY_ANALYZED = "Analysis is already done for all resumes"
ALL_RESUMES_ALREADY_ANALYZED_FOR_JOBS = (
    "Analysis is already done for all resumes in the specified jobs"
)
JOB_APPLICATION_FOREIGN_DATA_DELETED = (
    "Successfully deleted foreign data of job application"
)
JOB_APPLICATION_FOREIGN_DATA_DELETE_FAILED = (
    "Unable to delete foreign data of job application"
)
APPLICATION_ID_NOT_FOUND = "Application ID is not found"