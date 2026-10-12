import type { ComponentProps, ReactNode } from 'react';
import { buttonClasses, type ButtonVariant } from './buttonStyles';

interface ButtonProps extends ComponentProps<'button'> {
  variant?: ButtonVariant;
  children: ReactNode;
}

/**
 * The one button in the app. Keyboard focus, disabled state and the 44px touch
 * target are handled here so no screen has to remember them.
 */
export function Button({ variant = 'secondary', className = '', children, ...rest }: ButtonProps) {
  return (
    <button className={`${buttonClasses(variant)} ${className}`} {...rest}>
      {children}
    </button>
  );
}
