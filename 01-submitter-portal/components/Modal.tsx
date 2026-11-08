import React, { useEffect, useId, useRef } from 'react'
import Icon from './Icon'
export default function Modal({ isOpen, onClose, title, subtitle, children, maxWidth = '680px' }: { isOpen: boolean; onClose: () => void; title: string; subtitle?: string; children: React.ReactNode; maxWidth?: string }) {
  const ref = useRef<HTMLDialogElement>(null)
  const id = useId()
  useEffect(() => {
    const dialog = ref.current
    if (isOpen && dialog && !dialog.open) dialog.showModal()
    if (!isOpen && dialog?.open) dialog.close()
    return () => { if (dialog?.open) dialog.close() }
  }, [isOpen])
  return <dialog ref={ref} className="dialog" style={{ maxWidth }} aria-labelledby={id} onCancel={e => { e.preventDefault(); onClose() }} onClick={e => { if (e.target === e.currentTarget) { const r = e.currentTarget.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose() } }}>
    <header className="dialog-head"><div><h2 id={id}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" aria-label="Close dialog" onClick={onClose}><Icon name="close" /></button></header>
    <div className="dialog-body">{children}</div>
  </dialog>
}
