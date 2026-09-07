'use client'

export default function AdminScalingBanner() {
  return (
    <div className="scaling-banner">
      <div className="scaling-title">
        <small>COD OPS</small>
        <strong>MOVE TO SCALING TEAM</strong>
        <span>Build. Confirm. Deliver. Scale.</span>
      </div>

      <div className="runner-track">
        <div className="runner-group">

          <div className="follow-text">
            MOVE TO SCALING TEAM
          </div>

          <div className="runner">
            <svg
              viewBox="0 0 120 120"
              width="95"
              height="95"
              aria-hidden="true"
            >
              <circle cx="67" cy="20" r="11" fill="#ff7a00"/>

              <path
                d="M62 34 L48 61 L66 70 L78 45 Z"
                fill="#2563eb"
                stroke="white"
                strokeWidth="5"
                strokeLinejoin="round"
              />

              <path
                d="M51 46 L31 60"
                stroke="#ff7a00"
                strokeWidth="9"
                strokeLinecap="round"
              />

              <path
                d="M73 46 L94 57"
                stroke="#ff7a00"
                strokeWidth="9"
                strokeLinecap="round"
              />

              <path
                d="M61 69 L39 96"
                stroke="#2563eb"
                strokeWidth="11"
                strokeLinecap="round"
              />

              <path
                d="M66 69 L91 91"
                stroke="#ff7a00"
                strokeWidth="11"
                strokeLinecap="round"
              />

              <path
                d="M27 97 L43 97"
                stroke="white"
                strokeWidth="7"
                strokeLinecap="round"
              />

              <path
                d="M87 94 L104 94"
                stroke="white"
                strokeWidth="7"
                strokeLinecap="round"
              />
            </svg>
          </div>

          <div className="runner-shadow" />
        </div>
      </div>

      <style jsx>{`
        .scaling-banner{
          position:relative;
          min-height:190px;
          margin:0 0 24px;
          border-radius:24px;
          overflow:hidden;
          padding:26px 28px;
          background:
            radial-gradient(circle at 80% 10%,rgba(255,122,0,.25),transparent 30%),
            linear-gradient(120deg,#071426,#10264a 55%,#164cc9);
          box-shadow:0 18px 45px rgba(15,23,42,.16);
          color:white;
        }

        .scaling-banner:after{
          content:'';
          position:absolute;
          left:0;
          right:0;
          bottom:28px;
          height:3px;
          background:linear-gradient(
            90deg,
            transparent,
            rgba(255,255,255,.35),
            transparent
          );
        }

        .scaling-title{
          position:relative;
          z-index:3;
          max-width:480px;
        }

        .scaling-title small{
          display:block;
          font-size:11px;
          font-weight:800;
          letter-spacing:.2em;
          color:#93c5fd;
          margin-bottom:8px;
        }

        .scaling-title strong{
          display:block;
          font-size:30px;
          line-height:1.05;
          font-weight:900;
        }

        .scaling-title span{
          display:block;
          margin-top:10px;
          color:#cbd5e1;
          font-size:14px;
        }

        .runner-track{
          position:absolute;
          left:0;
          right:0;
          bottom:25px;
          height:110px;
          overflow:hidden;
          z-index:2;
        }

        .runner-group{
          position:absolute;
          left:-260px;
          bottom:2px;
          width:300px;
          height:105px;
          animation:moveAcross 8s linear infinite;
        }

        .runner{
          position:absolute;
          right:0;
          bottom:4px;
          animation:jump .55s ease-in-out infinite alternate;
          filter:drop-shadow(0 8px 14px rgba(0,0,0,.18));
        }

        .follow-text{
          position:absolute;
          right:83px;
          top:8px;
          padding:9px 15px;
          border-radius:999px;
          white-space:nowrap;
          font-size:12px;
          font-weight:900;
          letter-spacing:.08em;
          background:rgba(255,255,255,.14);
          border:1px solid rgba(255,255,255,.22);
          backdrop-filter:blur(9px);
          animation:textPulse .8s ease-in-out infinite alternate;
        }

        .runner-shadow{
          position:absolute;
          right:15px;
          bottom:0;
          width:65px;
          height:11px;
          border-radius:50%;
          background:rgba(0,0,0,.28);
          filter:blur(4px);
          animation:shadowPulse .55s ease-in-out infinite alternate;
        }

        @keyframes moveAcross{
          from{
            transform:translateX(0);
          }
          to{
            transform:translateX(calc(100vw + 450px));
          }
        }

        @keyframes jump{
          from{
            transform:translateY(0) rotate(-3deg);
          }
          to{
            transform:translateY(-18px) rotate(3deg);
          }
        }

        @keyframes textPulse{
          from{
            transform:scale(1);
          }
          to{
            transform:scale(1.08);
          }
        }

        @keyframes shadowPulse{
          from{
            transform:scaleX(1);
            opacity:.35;
          }
          to{
            transform:scaleX(.65);
            opacity:.16;
          }
        }

        @media(max-width:700px){
          .scaling-banner{
            min-height:220px;
            padding:22px;
          }

          .scaling-title strong{
            font-size:24px;
          }

          .runner-track{
            height:100px;
          }

          .runner svg{
            width:80px;
            height:80px;
          }
        }

        @media(prefers-reduced-motion:reduce){
          .runner-group,
          .runner,
          .follow-text,
          .runner-shadow{
            animation:none;
          }
        }
      `}</style>
    </div>
  )
}
