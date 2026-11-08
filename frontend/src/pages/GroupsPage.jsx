/** /groups page. */

import { RecentGroupList } from '../components/groups/RecentGroupList'
import { AppRefreshCard } from '../components/system/AppRefreshCard'
import { StorageStatus } from '../components/system/StorageStatus'

export function GroupsPage() {
  return (
    <div className="mx-auto flex w-full max-w-screen-md flex-col gap-6">
      <RecentGroupList />
      <AppRefreshCard />
      <StorageStatus />
    </div>
  )
}
