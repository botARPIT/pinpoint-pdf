import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, CheckCircle2, X, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

interface FileUploaderProps {
  onUploadComplete: (docId: string, filename: string) => void;
}

export function FileUploader({ onUploadComplete }: FileUploaderProps) {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles?.length > 0) {
      setFile(acceptedFiles[0]);
      setError(null);
      setProgress(0);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
    multiple: false,
  });

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress(0);
    setError(null);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const response = await api.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          setProgress(Math.round((progressEvent.loaded * 100) / (progressEvent.total || 1)));
        },
      });
      if (response.status === 202 || response.status === 200) {
        onUploadComplete(response.data.doc_id, response.data.filename);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed. Please try again.');
      setUploading(false);
    }
  };

  const removeFile = () => {
    setFile(null);
    setProgress(0);
    setError(null);
  };

  return (
    <div className="w-full max-w-lg mx-auto">
      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={cn(
          'relative rounded-2xl p-10 text-center cursor-pointer transition-all duration-300 overflow-hidden',
          isDragActive ? 'scale-[1.02]' : 'scale-100'
        )}
        style={{
          background: isDragActive
            ? 'rgba(244,63,94,0.08)'
            : file
              ? 'rgba(74,222,128,0.05)'
              : 'rgba(255,255,255,0.03)',
          border: `2px dashed ${isDragActive ? '#f43f5e' : file ? 'rgba(74,222,128,0.4)' : 'rgba(255,255,255,0.1)'}`,
          boxShadow: isDragActive ? '0 0 40px rgba(244,63,94,0.15), inset 0 0 40px rgba(244,63,94,0.03)' : 'none'
        }}
      >
        <input {...getInputProps()} />

        {/* Background glow on drag */}
        {isDragActive && (
          <div className="absolute inset-0 pointer-events-none" style={{
            background: 'radial-gradient(ellipse at center, rgba(244,63,94,0.08) 0%, transparent 70%)'
          }} />
        )}

        <div className="relative z-10 flex flex-col items-center gap-4">
          <div className="p-4 rounded-2xl transition-all duration-300" style={{
            background: file
              ? 'rgba(74,222,128,0.1)'
              : isDragActive
                ? 'rgba(244,63,94,0.15)'
                : 'rgba(255,255,255,0.05)'
          }}>
            {file
              ? <CheckCircle2 className="w-8 h-8" style={{ color: '#4ade80' }} />
              : <UploadCloud className="w-8 h-8 transition-colors" style={{ color: isDragActive ? '#fb7185' : 'rgba(255,255,255,0.3)' }} />
            }
          </div>

          <div className="space-y-1">
            {file ? (
              <>
                <p className="text-sm font-semibold text-white">{file.name}</p>
                <p className="text-xs" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-white/70">
                  {isDragActive ? 'Drop it here!' : 'Drop your PDF here'}
                </p>
                <p className="text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
                  or click to browse · PDF up to 50MB
                </p>
              </>
            )}
          </div>
        </div>
      </div>

      {/* File actions + progress */}
      {file && (
        <div className="mt-4 space-y-3 animate-slide-up">
          {!uploading && (
            <div className="flex gap-2">
              <button
                onClick={removeFile}
                className="flex-none px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 hover:bg-white/5"
                style={{ color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)' }}
              >
                <X className="w-4 h-4" />
              </button>
              <button
                onClick={handleUpload}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white btn-rose"
              >
                <span className="flex items-center justify-center gap-2">
                  <FileText className="w-4 h-4" />
                  Upload & Process
                </span>
              </button>
            </div>
          )}

          {uploading && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs mb-1" style={{ color: 'rgba(255,255,255,0.4)' }}>
                <span>Uploading…</span>
                <span style={{ color: '#fb7185' }}>{progress}%</span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                <div
                  className="h-full rounded-full transition-all duration-300 animate-shimmer"
                  style={{
                    width: `${progress}%`,
                    background: 'linear-gradient(90deg, #fb7185, #f43f5e, #fb7185)',
                    backgroundSize: '200% 100%'
                  }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-xl px-4 py-3 text-sm animate-fade-in" style={{
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.2)',
              color: '#fca5a5'
            }}>
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
