' Punto de entrada. Crea la pantalla y pasa a la escena los argumentos de
' arranque y las órdenes que llegan desde la web mientras la app está abierta.
sub Main(args as Dynamic)
    screen = CreateObject("roSGScreen")
    port = CreateObject("roMessagePort")
    screen.SetMessagePort(port)
    scene = screen.CreateScene("MainScene")
    screen.Show()

    input = CreateObject("roInput")
    input.SetMessagePort(port)
    scene.launchArgs = args

    while true
        msg = wait(0, port)
        msgType = type(msg)
        if msgType = "roSGScreenEvent"
            if msg.IsScreenClosed() then return
        else if msgType = "roInputEvent"
            if msg.IsInput() then scene.inputArgs = msg.GetInfo()
        end if
    end while
end sub
