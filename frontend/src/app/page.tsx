import { AppSidebar } from "@/components/dashboard/app-sidebar";
import { ApprovalModal } from "@/components/dashboard/approval-modal";
import { ChatPanel } from "@/components/dashboard/chat-panel";
import { TaskLogPanel } from "@/components/dashboard/task-log-panel";

export default function DashboardPage() {
  return (
    <div className="flex h-screen w-full overflow-hidden">
      <AppSidebar />
      <ChatPanel />
      <TaskLogPanel />
      <ApprovalModal />
    </div>
  );
}
