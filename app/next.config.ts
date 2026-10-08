import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingIncludes: {
    "/*": ["./snapshot/**/*"],
  },
};

export default nextConfig;
