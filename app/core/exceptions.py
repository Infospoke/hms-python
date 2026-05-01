from app.core import config as consts
from fastapi import status


class ATSException(Exception):

    def __init__(
        self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    ):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class HTTPClientException(ATSException):

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        original_error: Exception = None,
    ):
        self.original_error = original_error
        super().__init__(message, status_code)


class GeminiAPIException(HTTPClientException):
    pass


class DatabaseException(ATSException):
    pass


class DatabaseConnectionException(DatabaseException):

    def __init__(self, message: str = consts.FAILED_TO_CONNECT_TO_DB):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)


class DatabaseQueryException(DatabaseException):

    def __init__(self, message: str, query_type: str = "unknown"):
        self.query_type = query_type
        super().__init__(
            consts.DB_QUERY_FAILED(query_type, message),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class DatabaseIntegrityException(DatabaseException):

    def __init__(self, message: str):
        super().__init__(
            consts.DB_INTEGRITY_ERROR(message), status.HTTP_400_BAD_REQUEST
        )


class ResumeProcessingException(ATSException):
    pass


class ResumeParsingException(ResumeProcessingException):

    def __init__(self, filename: str, message: str):
        self.filename = filename
        super().__init__(
            consts.RESUME_PARSE_FAILED(filename, message),
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


class ValidationException(ATSException):

    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(message, status.HTTP_400_BAD_REQUEST)


class ResourceNotFoundException(ATSException):

    def __init__(self, resource_type: str, identifier: str = None):
        if identifier:
            message = consts.RESOURCE_NOT_FOUND_BY_IDENTIFIER(resource_type, identifier)
        else:
            message = consts.RESOUNE_NOT_FOUND(resource_type)
        super().__init__(message, status.HTTP_404_NOT_FOUND)


class DuplicateResourceException(ATSException):

    def __init__(self, resource_type: str, identifier: str = None):
        if identifier:
            message = consts.RESOURCE_ALREADY_EXISTS_BY_IDENTIFIER(
                resource_type, identifier
            )
        else:
            message = consts.RESOURCE_ALREADY_EXISTS(resource_type)
        super().__init__(message, status.HTTP_409_CONFLICT)


class FileOperationException(ATSException):

    def __init__(self, message: str, filename: str = None):
        self.filename = filename
        if filename:
            message = consts.FILE_OPERATION_ERROR_ON_FILE(filename, message)
        else:
            message = consts.FILE_OPERATION_ERROR(message)
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)
