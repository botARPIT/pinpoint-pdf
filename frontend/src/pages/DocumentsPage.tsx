import { useEffect, useState } from 'react';
import { Trash2, FileText, PlusCircle, Clock, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import api from '@/lib/api';
import type { Document } from '@/lib/types';
import { Link } from 'react-router-dom';

function StatusBadge({ status }: { status: string }) {
  const configs: Record<string, { icon: any; label: string; color: string; bg: string }> = {
    ready: { icon: CheckCircle2, label: 'Ready', color: '#4ade80', bg: 'rgba(74,222,128,0.1)' },
    failed: { icon: AlertCircle, label: 'Failed', color: '#f87171', bg: 'rgba(248,113,113,0.1)' },
    processing: { icon: Loader2, label: 'Processing', color: '#fb7185', bg: 'rgba(244,63,94,0.1)' },
    preprocessing: { icon: Loader2, label: 'Preprocessing', color: '#fb7185', bg: 'rgba(244,63,94,0.1)' },
    preprocessed: { icon: Loader2, label: 'Preprocessed', color: '#fb7185', bg: 'rgba(244,63,94,0.1)' },
    chunked: { icon: Loader2, label: 'Indexing', color: '#fb7185', bg: 'rgba(244,63,94,0.1)' },
    pending: { icon: Clock, label: 'Pending', color: 'rgba(255,255,255,0.4)', bg: 'rgba(255,255,255,0.06)' },
  };
  const c = configs[status] || configs.pending;
  const Icon = c.icon;
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium" style={{ background: c.bg, color: c.color }}>
      <Icon className={`w-3 h-3 ${['processing', 'preprocessing', 'chunked', 'preprocessed'].includes(status) ? 'animate-spin' : ''}`} />
      {c.label}
    </span>
  );
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [docToDelete, setDocToDelete] = useState<Document | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchDocuments = async () => {
    try {
      const response = await api.get('/documents');
      setDocuments(response.data.documents);
    } catch (error) {
      console.error('Failed to fetch documents', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDelete = async () => {
    if (!docToDelete) return;
    setDeleting(true);
    try {
      await api.delete(`/documents/${docToDelete.doc_id}`);
      setDocuments(prev => prev.filter(d => d.doc_id !== docToDelete.doc_id));
      setDocToDelete(null);
    } catch (error) {
      console.error('Failed to delete document', error);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8 animate-fade-in">
        <div>
          <h1 className="text-3xl font-bold text-white mb-1">Documents</h1>
          <p className="text-sm" style={{ color: 'rgba(255,255,255,0.35)' }}>
            {documents.length} document{documents.length !== 1 ? 's' : ''} in your knowledge base
          </p>
        </div>
        <Link to="/">
          <button className="btn-rose flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white">
            <PlusCircle className="w-4 h-4" />
            Upload New
          </button>
        </Link>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin" style={{ color: '#fb7185' }} />
        </div>
      )}

      {/* Empty state */}
      {!loading && documents.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center animate-fade-in">
          <div className="p-5 rounded-2xl mb-4" style={{ background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.15)' }}>
            <FileText className="w-10 h-10" style={{ color: '#fb7185' }} />
          </div>
          <h3 className="text-lg font-semibold text-white mb-2">No documents yet</h3>
          <p className="text-sm mb-6" style={{ color: 'rgba(255,255,255,0.35)' }}>Upload your first PDF to get started</p>
          <Link to="/">
            <button className="btn-rose px-5 py-2.5 rounded-xl text-sm font-semibold text-white">
              Upload a PDF
            </button>
          </Link>
        </div>
      )}

      {/* Card grid */}
      {!loading && documents.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {documents.map((doc, i) => (
            <div
              key={doc.doc_id}
              className="group relative rounded-2xl p-5 transition-all duration-200 animate-slide-up hover:scale-[1.01]"
              style={{
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.07)',
                animationDelay: `${i * 50}ms`
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = 'rgba(244,63,94,0.2)';
                (e.currentTarget as HTMLElement).style.background = 'rgba(244,63,94,0.04)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.07)';
                (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.03)';
              }}
            >
              {/* Delete button */}
              <button
                onClick={() => setDocToDelete(doc)}
                className="absolute top-4 right-4 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-200 hover:bg-red-500/15"
                style={{ color: 'rgba(255,255,255,0.3)' }}
                onMouseEnter={(e) => (e.currentTarget as HTMLElement).style.color = '#f87171'}
                onMouseLeave={(e) => (e.currentTarget as HTMLElement).style.color = 'rgba(255,255,255,0.3)'}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>

              {/* Icon */}
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4" style={{
                background: 'rgba(244,63,94,0.1)',
                border: '1px solid rgba(244,63,94,0.15)'
              }}>
                <FileText className="w-5 h-5" style={{ color: '#fb7185' }} />
              </div>

              {/* Filename */}
              <h3 className="text-sm font-semibold text-white mb-2 pr-6 leading-snug line-clamp-2">
                {doc.filename}
              </h3>

              {/* Meta */}
              <div className="flex items-center justify-between mt-3">
                <StatusBadge status={doc.status} />
                <span className="text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>
                  {new Date(doc.uploaded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete confirm dialog */}
      {docToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)' }}>
          <div className="glass-card rounded-2xl p-6 w-full max-w-md animate-slide-up" style={{ border: '1px solid rgba(239,68,68,0.2)' }}>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-xl" style={{ background: 'rgba(239,68,68,0.1)' }}>
                <Trash2 className="w-5 h-5" style={{ color: '#f87171' }} />
              </div>
              <h2 className="text-base font-semibold text-white">Delete document?</h2>
            </div>
            <p className="text-sm mb-6" style={{ color: 'rgba(255,255,255,0.45)' }}>
              This will permanently delete <span className="text-white font-medium">"{docToDelete.filename}"</span> and remove it from your knowledge base. This cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setDocToDelete(null)}
                className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 hover:bg-white/5"
                style={{ color: 'rgba(255,255,255,0.5)', border: '1px solid rgba(255,255,255,0.08)' }}
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200"
                style={{
                  background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                  boxShadow: '0 4px 12px rgba(239,68,68,0.3)'
                }}
              >
                {deleting ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
