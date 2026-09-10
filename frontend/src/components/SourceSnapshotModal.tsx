import DOMPurify from 'dompurify';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { api } from '../api/client';

interface SourceSnapshotModalProps {
  fileId: number;
  fallbackTitle: string;
  onClose: () => void;
}

export function SourceSnapshotModal({ fileId, fallbackTitle, onClose }: SourceSnapshotModalProps) {
  const { t } = useTranslation();
  const snapshotQuery = useQuery({
    queryKey: ['library-source-snapshot', fileId],
    queryFn: () => api.getLibrarySourceSnapshot(fileId),
  });
  const snapshot = snapshotQuery.data;
  const title = snapshot?.title || fallbackTitle;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-3xl overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-bambu-dark-tertiary p-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-bambu-green">
              {t('fileManager.sourceArchive')}
            </p>
            <h2 className="text-xl font-semibold text-white">{title}</h2>
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-bambu-dark" aria-label={t('common.close')}>
            <X className="h-5 w-5 text-bambu-gray" />
          </button>
        </div>

        <div className="max-h-[calc(90vh-5rem)] overflow-y-auto p-5">
          {snapshotQuery.isPending && (
            <div className="flex items-center justify-center gap-2 py-12 text-bambu-gray">
              <Loader2 className="h-5 w-5 animate-spin" />
              {t('common.loading')}
            </div>
          )}
          {snapshotQuery.isError && (
            <p className="py-8 text-center text-red-400">{t('fileManager.sourceArchiveLoadError')}</p>
          )}
          {snapshot && (
            <div className="space-y-5">
              {snapshot.images.length > 0 && (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {snapshot.images.map((image) => (
                    <img
                      key={image.name}
                      src={api.getLibrarySourceAssetUrl(fileId, image.name)}
                      alt={title}
                      className="aspect-square w-full rounded-lg bg-bambu-dark object-cover"
                    />
                  ))}
                </div>
              )}

              <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-bambu-gray">
                {snapshot.creator && <span>{t('makerworld.byCreator', { name: snapshot.creator })}</span>}
                {snapshot.license && <span>{t('makerworld.licensePrefix')}: {snapshot.license}</span>}
                <span>{t('fileManager.sourceCapturedAt', { date: new Date(snapshot.captured_at).toLocaleString() })}</span>
              </div>

              {snapshot.description_html && (
                <div
                  className="prose prose-sm max-w-none text-white dark:prose-invert"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(snapshot.description_html) }}
                />
              )}

              <a
                href={snapshot.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-bambu-green hover:underline"
              >
                <ExternalLink className="h-4 w-4" />
                {t('makerworld.openOnMakerworld')}
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
