import { HrKnowledgeApp } from "@/components/HrKnowledgeApp";
import { SystemDialogProvider } from "@/components/SystemDialog";

export default function HomePage() {
  return <SystemDialogProvider><HrKnowledgeApp /></SystemDialogProvider>;
}
