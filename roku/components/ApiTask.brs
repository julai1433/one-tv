sub init()
    m.top.functionName = "fetch"
end sub

sub fetch()
    xfer = CreateObject("roUrlTransfer")
    port = CreateObject("roMessagePort")
    xfer.SetMessagePort(port)
    xfer.SetUrl(m.top.url)
    xfer.EnableEncodings(true)
    err = "no se pudo conectar"
    if m.top.body <> ""
        xfer.AddHeader("Content-Type", "application/json")
        started = xfer.AsyncPostFromString(m.top.body)
    else
        started = xfer.AsyncGetToString()
    end if
    if started
        msg = wait(20000, port)
        if msg = invalid
            xfer.AsyncCancel()
            err = "sin respuesta"
        else if msg.GetResponseCode() = 200
            data = ParseJson(msg.GetString())
            if data <> invalid
                m.top.result = data
                m.top.error = ""
                m.top.done = true
                return
            end if
            err = "respuesta inválida"
        else
            err = "HTTP " + msg.GetResponseCode().ToStr() + " " + msg.GetFailureReason()
        end if
    end if
    m.top.error = err
    m.top.done = true
end sub
