from typing import Optional

# Base Exception
class DirectoryTranslationError(Exception):
    """Base exception for the directory translation tool."""
    pass

# Project Config Errors
class ProjectConfigError(DirectoryTranslationError):
    """Base exception for project configuration errors."""
    pass

class LoadConfigError(ProjectConfigError):
    """Errors related to loading project configuration."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception

class WriteConfigError(ProjectConfigError):
    """Errors related to writing project configuration."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception

class MigrateConfigError(ProjectConfigError):
    """Errors related to migrating project configuration."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception

# Project Errors
class ProjectError(DirectoryTranslationError):
    """Base exception for general project operations."""
    pass

class InitProjectError(ProjectError):
    """Errors during project initialization."""
    pass

class InvalidPathError(InitProjectError, ValueError): # Can also be a general error
    """Invalid path provided."""
    pass

class ProjectAlreadyInitializedError(InitProjectError):
    """Project is already initialized in the target location."""
    pass

class LoadProjectError(ProjectError):
    """Errors during project loading."""
    pass

class NoConfigFoundError(LoadProjectError):
    """No configuration file found for the project."""
    pass

class SetLLMServiceError(ProjectError):
    """Errors when setting the llm service."""
    pass

class SetTypstConfigError(ProjectError):
    """Errors when setting Typst parser configuration."""
    pass

class SetLatexConfigError(ProjectError):
    """Errors when setting LaTeX parser configuration."""
    pass
class SetSourceDirError(ProjectError):
    """Errors when setting the source directory."""
    pass

class DirectoryDoesNotExistError(SetSourceDirError, FileNotFoundError):
    """Referenced directory does not exist."""
    pass

class NotADirectoryError(SetSourceDirError, NotADirectoryError): # Python's built-in
    """Provided path is not a directory."""
    pass

class AnalyzeDirError(SetSourceDirError):
    """Error analyzing directory structure."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception

class LangAlreadyInProjectError(ProjectError): # Used by SetSourceDir, AddLanguage
    """Language is already part of the project (either as source or target)."""
    pass

class AddLanguageError(ProjectError):
    """Errors when adding a new target language."""
    pass

class NoSourceLanguageError(ProjectError): # Used by various operations
    """Operation requires a source language to be set, but none is."""
    pass

class NoSourceDirError(ProjectError): # Used by various operations
    """Operation requires a source directory to be set, but none is."""
    pass

class LangDirExistsError(AddLanguageError):
    """The directory for the language already exists."""
    pass

class AddCustomLanguageError(ProjectError):
    """Errors when adding a custom language to the project."""
    pass

class RemoveCustomLanguageError(ProjectError):
    """Errors when removing a custom language from the project."""
    pass

class RemoveLanguageError(ProjectError):
    """Errors when removing a language."""
    pass

class LangDirDoesNotExistError(RemoveLanguageError, FileNotFoundError):
    """Language directory does not exist when it's expected to."""
    pass

class TargetLanguageNotInProjectError(ProjectError): # Used by RemoveLang, Translate
    """The specified target language is not configured in the project."""
    pass


class SyncFilesError(ProjectError):
    """Errors during file synchronization."""
    pass

class NoTargetLanguagesError(SyncFilesError):
    """No target languages configured for synchronization or translation."""
    pass

class CopyFileDirError(DirectoryTranslationError): # Can be used by SyncFiles
    """Errors during file/directory copying."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception

class AddTranslatableFileError(ProjectError):
    """Errors when marking a file as translatable or untranslatable."""
    pass

class FileDoesNotExistError(AddTranslatableFileError, FileNotFoundError): # General purpose
    """Referenced file does not exist."""
    pass


class GetTranslatableFilesError(ProjectError):
    """Errors when retrieving list of translatable files."""
    # NoSourceLang is the primary error here, covered by NoSourceLanguageError
    pass

class TranslateFileError(ProjectError):
    """Errors during file translation."""
    pass

class UntranslatableFileError(TranslateFileError):
    """Attempting to translate a file not marked as translatable."""
    pass

class TranslationProcessError(TranslateFileError):
    """Generic error during the translation API call or processing."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception


class ChunkTranslationFailed(TranslateFileError):
    """Signals that a chunk could not be translated and should be left unchanged."""

    def __init__(self, chunk: str, original_exception: Optional[Exception] = None):
        super().__init__("Chunk translation failed.")
        self.chunk = chunk
        self.original_exception = original_exception


class PlaceholderVerificationError(TranslateFileError):
    """Raised when <PH> tags are missing or duplicated in the translated XML."""

    def __init__(self, missing: list[str], extra: list[str] | None = None):
        msg_parts = []
        if missing:
            msg_parts.append(f"missing PH IDs: {missing}")
        if extra:
            msg_parts.append(f"extra PH IDs: {extra}")
        super().__init__("Placeholder verification failed: " + "; ".join(msg_parts))
        self.missing = missing
        self.extra = extra or []
       
class CorrectTranslationError(ProjectError):
    """
    Errors when correcting translation
    """
    pass

class TranslationCacheSyncError(ProjectError):
    """Errors raised while rebuilding/syncing the translation cache."""
    pass

class TranslationCacheClearError(ProjectError):
    """Errors raised while clearing the translation cache."""
    pass

class CorrectingTranslationError(CorrectTranslationError):
    """
    Correcting translation error
    """
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception

class ChecksumNotFoundError(CorrectTranslationError):
    """
    Checksum not found in the cache
    """
    pass

class NoSourceFileError(CorrectTranslationError):
    """
    No source file for the given translated file
    """
    pass
