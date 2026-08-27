export interface UserProfile {
  id: string;
  email: string;
  merchantName?: string;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
}
