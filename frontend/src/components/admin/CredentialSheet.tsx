import React from 'react';
import { notify } from '../../services/notify';

export interface Credential {
  loginId: string;
  temporaryPassword: string;
  displayName?: string;
}

interface CredentialSheetProps {
  credential: Credential;
  onClose: () => void;
}

/** One-time credential hand-off sheet (roadmap task P1-09). Shown exactly
 * once, right after an account is created or its password is reset — the
 * temporary password is returned in that single API response and never
 * stored anywhere the admin could come back and look it up later, so this
 * component is the only place it is ever visible. */
const CredentialSheet: React.FC<CredentialSheetProps> = ({ credential, onClose }) => {
  const closeButtonRef = React.useRef<HTMLButtonElement>(null);

  React.useEffect(() => {
    closeButtonRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const handleCopy = async () => {
    const text = `Login: ${credential.loginId}\nTemporary password: ${credential.temporaryPassword}`;
    try {
      await navigator.clipboard.writeText(text);
      notify('Credentials copied to clipboard.', { kind: 'success' });
    } catch {
      notify('Could not copy automatically — please copy the text manually.', { kind: 'error' });
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="credential-sheet-title"
      aria-describedby="credential-sheet-desc"
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
    >
      <div className="glass-card bg-white rounded-3xl p-8 max-w-md w-full space-y-5 shadow-2xl">
        <div>
          <h2 id="credential-sheet-title" className="font-heading text-xl font-bold text-on-surface">
            Account credentials
          </h2>
          <p id="credential-sheet-desc" className="text-sm text-on-surface-variant font-body mt-1">
            Shown once. Hand this to {credential.displayName || 'the user'} directly — it is not
            saved anywhere you can come back to later.
          </p>
        </div>

        <dl className="space-y-3">
          <div className="bg-surface-container-low rounded-xl p-4">
            <dt className="text-xs font-heading font-semibold text-on-surface-variant uppercase tracking-wider">
              Login
            </dt>
            <dd className="font-mono text-sm text-on-surface mt-1 break-all">{credential.loginId}</dd>
          </div>
          <div className="bg-surface-container-low rounded-xl p-4">
            <dt className="text-xs font-heading font-semibold text-on-surface-variant uppercase tracking-wider">
              Temporary password
            </dt>
            <dd className="font-mono text-lg font-bold text-primary mt-1 tracking-wider">
              {credential.temporaryPassword}
            </dd>
          </div>
        </dl>

        <p className="text-xs text-on-surface-variant font-body">
          They will be asked to choose their own password the first time they sign in.
        </p>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleCopy}
            className="flex-1 px-4 py-2.5 rounded-xl border border-outline-variant text-sm font-heading font-semibold text-on-surface hover:bg-surface-variant/30 transition-all"
          >
            Copy
          </button>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl bg-primary-container text-white text-sm font-heading font-semibold hover:bg-primary transition-all"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export default CredentialSheet;
