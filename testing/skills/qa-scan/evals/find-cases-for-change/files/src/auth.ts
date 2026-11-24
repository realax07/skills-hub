import jwt from "jsonwebtoken";
import type { Request, Response, NextFunction } from "express";

export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const token = (req.headers.authorization || "").replace("Bearer ", "");
  try {
    (req as any).user = jwt.verify(token, process.env.JWT_SECRET!);
    next();
  } catch {
    res.status(401).json({ error: "unauthorized" });
  }
}

export function requireRole(role: "MANAGER" | "ADMIN") {
  return (req: Request, res: Response, next: NextFunction) => {
    const user = (req as any).user;
    if (user.role === "ADMIN" || user.role === role) return next();
    res.status(403).json({ error: "forbidden" });
  };
}
