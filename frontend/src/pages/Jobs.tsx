import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getJobs, Job, JobStatus, manageJobAction } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, Pause, Play, X, RotateCcw } from "lucide-react";
import { toast } from "sonner";

const groups: { title: string; statuses: JobStatus[] }[] = [
  { title: "Running", statuses: ["running"] },
  { title: "Queued / Paused", statuses: ["queued", "paused"] },
  { title: "Completed", statuses: ["completed"] },
  { title: "Cancelled", statuses: ["cancelled"] },
  { title: "Failed", statuses: ["failed"] },
];

const statusColor: Record<JobStatus, string> = {
  queued: "bg-muted text-muted-foreground",
  running: "bg-primary/20 text-primary border border-primary/40",
  paused: "bg-warning/20 text-warning-foreground border border-warning/40",
  completed: "bg-success/20 text-success border border-success/40",
  cancelled: "bg-muted text-muted-foreground",
  failed: "bg-destructive/20 text-destructive border border-destructive/40",
};

function JobCard({ job }: { job: Job }) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: (action: "pause" | "resume" | "cancel" | "retry") =>
      manageJobAction(job.id, action),
    onSuccess: (r) => {
      toast.success(r.message || "Done");
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["books"] });
    },
    onError: (e) => toast.error((e as { message?: string })?.message ?? "Action failed"),
  });

  return (
    <Card className="p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold truncate">{job.bookTitle ?? `Book #${job.book_id}`}</div>
          <div className="text-xs text-muted-foreground">
            {job.label ?? job.type}
            {job.createdAt && <> · {new Date(job.createdAt).toLocaleString()}</>}
          </div>
        </div>
        <Badge variant="outline" className={statusColor[job.status]}>
          {job.status}
        </Badge>
      </div>
      {(job.status === "running" || job.status === "queued" || job.status === "paused") && (
        <div className="mt-3 space-y-1">
          <Progress value={job.progress} />
          <div className="text-xs text-muted-foreground text-right">{job.progress}%</div>
        </div>
      )}
      {job.status === "failed" && job.note && (
        <p className="mt-2 text-xs text-destructive">{job.note}</p>
      )}
      <div className="flex gap-2 mt-3">
        {job.status === "running" && (
          <Button size="sm" variant="outline" onClick={() => mut.mutate("pause")}>
            <Pause className="size-3" /> Pause
          </Button>
        )}
        {job.status === "paused" && (
          <Button size="sm" variant="outline" onClick={() => mut.mutate("resume")}>
            <Play className="size-3" /> Resume
          </Button>
        )}
        {(job.status === "running" || job.status === "queued" || job.status === "paused") && (
          <Button size="sm" variant="outline" onClick={() => mut.mutate("cancel")}>
            <X className="size-3" /> Cancel
          </Button>
        )}
        {job.status === "failed" && (
          <Button size="sm" variant="outline" onClick={() => mut.mutate("retry")}>
            <RotateCcw className="size-3" /> Retry
          </Button>
        )}
      </div>
    </Card>
  );
}

export default function Jobs() {
  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: getJobs,
    refetchInterval: (q) => {
      const data = q.state.data as Job[] | undefined;
      return data?.some((j) => j.status === "queued" || j.status === "running") ? 5000 : false;
    },
  });

  return (
    <div className="p-6 md:p-8 max-w-5xl">
      <h1 className="text-3xl font-bold tracking-tight mb-6">Jobs</h1>
      {isLoading ? (
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      ) : jobs.length === 0 ? (
        <p className="text-muted-foreground">No jobs yet.</p>
      ) : (
        <div className="space-y-8">
          {groups.map((g) => {
            const items = jobs.filter((j) => g.statuses.includes(j.status));
            if (items.length === 0) return null;
            return (
              <section key={g.title}>
                <h2 className="text-sm uppercase tracking-wider text-muted-foreground font-semibold mb-3">
                  {g.title} <span className="ml-1">({items.length})</span>
                </h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {items.map((j) => (
                    <JobCard key={j.id} job={j} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
