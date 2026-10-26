/** /groups page. */

import { RecentGroupList } from '../components/groups/RecentGroupList'
import { BackupControls } from '../components/system/BackupControls'

export function GroupsPage() {
  return (
    <div className="mx-auto flex w-full max-w-screen-md flex-col gap-6">
      <RecentGroupList />
      <BackupControls />
    </div>
  )
}
