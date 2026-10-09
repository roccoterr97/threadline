import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { buttonClasses, type ButtonVariant } from './buttonStyles';
import { OutsideMark } from './OutsideMark';

interface ButtonLinkProps {
  to: string;
  variant?: ButtonVariant;
  className?: string;
  children: ReactNode;
}

/** A link that looks like a button. An outside address opens in a new tab. */
export function ButtonLink({ to, variant = 'primary', className = '', children }: ButtonLinkProps) {
  const classes = buttonClasses(variant, className);
  if (/^https?:\/\//.test(to)) {
    return (
      <a href={to} className={classes} target="_blank" rel="noreferrer">
        {children}
        <OutsideMark />
      </a>
    );
  }
  return (
    <Link to={to} className={classes}>
      {children}
    </Link>
  );
}
