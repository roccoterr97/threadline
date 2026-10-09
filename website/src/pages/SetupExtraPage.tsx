import { Navigate, useParams } from 'react-router-dom';
import { SETUP_GUIDE } from '../setup/guide';
import { useSetupProgress } from '../setup/progress';
import { extraSequence, screenPath } from '../setup/wizard';
import { NoSuchScreen } from './NoSuchScreen';

/** The door into one extra: it opens the extra's first screen. */
export function SetupExtraPage() {
  const { partId } = useParams();
  const progress = useSetupProgress();
  const sequence = partId === undefined ? null : extraSequence(SETUP_GUIDE, partId, progress);
  const first = sequence?.[0];
  if (first === undefined) return <NoSuchScreen />;
  return <Navigate to={screenPath(first)} replace />;
}
